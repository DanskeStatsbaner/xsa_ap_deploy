def call(String daProject = 'defaultProject') {
    pipeline {

        agent {
            label "linux"
        }
        parameters {
            booleanParam(name: 'TagLatest', defaultValue: false, description: 'Tag this image as latest')
        }
        options {
            buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '30'))
            timestamps()
            disableConcurrentBuilds()
        }
        environment {
            daProject = "${env.GIT_URL.replaceFirst(/^.*\/([^\/]+?).git$/, '$1')}"
            projectName  = "${daProject.toLowerCase()}"
            deployTo = "sit"
            version = "1.0.0.${env.BUILD_NUMBER}"
            suffix = "${env.GIT_COMMIT}-${env.GIT_BRANCH.replace('/', '-')}"
            packageVersion = "${version}-${suffix}"
            jobName = "${daProject.toUpperCase()}"
            artifactoryServerId = "artifactory"
            manifest = "manifest.yml"
            findPython = "type: python"
            findScopes = "xs-security.json"
            apiKey = credentials("Octopus-Api")
            octoName = projectName.toUpperCase()
            firstCharInProject = "${daProject.substring(0, 1).toUpperCase()}"
            parentProject = "XSA_MASTER_AP"
            octoUrl = "https://octopus.azure.dsb.dk"
            basepath = "${basepath}"
        }

        stages {
            stage ("Octopus Project Sync") {
                agent { label "windows" }
                steps {
                    bat 'del *.nupkg'
                    bat 'del *.zip'

                    rtDownload(
                        spec: '''{ "files": [
                            {
                                "pattern": "octopus-dataarten/dataART.xsa_octopus.*",
                                "sortBy": ["created"],
                                "sortOrder": "desc",
                                "limit": 1
                            }
                        ] }''',
                        serverId: "${artifactoryServerId}"
                    )

                    bat 'ren *.nupkg xsa_octopus.zip'
                    unzip zipFile: "xsa_octopus.zip"

                    bat 'xcopy SpaceCloner-master\\* .\\* /s /e /i /y'

                    powershell """
                        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
                        ./SetupOctopusProject.ps1 -fromProjectName $parentProject -toProjectName $octoName -octopusUrl $octoUrl -octopusApiKey $apiKey
                        """
                }
            }

            stage ("Check Code") {
                steps {
                    echo "*** Checking manifest for info ***"
                    script {
                        def status = sh returnStatus: true, script:"grep -ir --include 'manifest.yml' '${findPython}' . "
                        if (status==0) {
                            println("Python Project Found")
                            def appcheck = sh returnStatus: true, script:"find . -name '${findScopes}'"
                            if (appcheck==0) {
                                println("WebAppFound")
                            } else {
                                println("SystemAppFound")
                            }
                        } else {
                            println("No supported project-type found - The pipeline currently supports following project types (Python)")
                            sh "exit 1"
                        }
                    }
                    echo "*** Code Check Completed ***"
                }

            }


            stage ("Prepare Artifacts") {
                agent {
                    docker {
                        image "${artifactoryDocker}/xsa_mta_builder:latest"
                        registryUrl "http://${artifactoryDocker}"
                        registryCredentialsId 'Artifactory'
                        reuseNode true
                    }
                }
                steps {
                    fileOperations([
                        fileDeleteOperation(includes: 'dataART.xsa_ap_deploy.*')
                    ])

                    rtDownload(
                        spec: '''{ "files": [
                            {
                                "pattern": "octopus-dataarten/dataART.xsa_ap_deploy.*",
                                "sortBy": ["created"],
                                "sortOrder": "desc",
                                "limit": 1
                            }
                        ] }''',
                        serverId: "${artifactoryServerId}"
                    )

                    sh "cp dataART.xsa_ap_deploy.*.nupkg dataART.xsa_ap_deploy.zip"

                    unzip zipFile: "$WORKSPACE/dataART.xsa_ap_deploy.zip", dir: "$WORKSPACE"

                    stash includes: "deployment/app-router/*", name: "appRouter", useDefaultExcludes: false
                    stash includes: "deployment/app/*", name: "app", useDefaultExcludes: false
                    stash includes: "deployment/app/framework/*", name: "appFramework", useDefaultExcludes: false
                    stash includes: "octopus/*", name: "octopus", useDefaultExcludes: false
                }
            }

            stage ("Publish Artifacts") {
                agent {
                    docker {
                        image "octopusdeploy/octo"
                        args '--entrypoint=\'\''
                    }
                }
                steps {
                    unstash "appRouter"
                    unstash "app"
                    unstash "appFramework"
                    unstash "octopus"

                    sh "rm -rf dataART.${projectName}.${version}"

                    fileOperations([
                        folderCopyOperation(
                            sourceFolderPath: "octopus",
                            destinationFolderPath: "${basepath}/octopus"),
                        folderCopyOperation(
                            sourceFolderPath: "app",
                            destinationFolderPath: "${basepath}/app"),
                        folderCopyOperation(
                            sourceFolderPath: "deployment/app-router",
                            destinationFolderPath: "${basepath}/app-router"),
                        folderCopyOperation(
                            sourceFolderPath: "deployment/app/framework",
                            destinationFolderPath: "${basepath}/app/framework"),
                        fileCopyOperation(
                            flattenFiles: true,
                            includes: "*.*",
                            excludes: "*.nupkg",
                            targetLocation: "${basepath}"),
                        fileCopyOperation(
                            flattenFiles: true,
                            includes: "deployment/app/*.*",
                            targetLocation: "${basepath}/app"),
                        folderDeleteOperation(
                            folderPath: "${basepath}/deployment")
                    ])
                    script {
                        def appcheck = sh returnStatus: true, script:"find . -name '${findScopes}'"
                        if (appcheck != 0) {
                            fileOperations([
                                folderDeleteOperation(folderPath: "${basepath}/app-router")
                            ])
                        }
                    }

                    sh """ octo pack --id="dataART.${projectName}" --version="${packageVersion}" --basepath="${basepath}" --outFolder=$WORKSPACE """

                    rtUpload(
                        spec: '''{ "files": [
                            {
                                "pattern": "dataART.${projectName}.${packageVersion}.nupkg",
                                "target": "octopus-dataarten/"
                            }
                        ] }''',
                        buildNumber: "${packageVersion}", buildName: "dataART.${projectName}",
                        serverId: "${artifactoryServerId}"
                    )
                    rtPublishBuildInfo(buildNumber: "${packageVersion}", buildName: "dataART.${projectName}", serverId: "${artifactoryServerId}")
                }
            }
            stage ("Octopus sit") {
                agent {
                    docker {
                        image "octopusdeploy/octo"
                        args '--entrypoint=\'\''
                    }
                }
                options { skipDefaultCheckout true }
                environment {
                    deployTo = "sit"
                    releaseversion = "${version}"
                    OCTOPUS_CLI_SERVER = "https://octopus.azure.dsb.dk"
                    OCTOPUS_CLI_API_KEY = credentials("Octopus-Api")
                    hostargs = "--project ${jobName} --version=${releaseversion} --space=Spaces-3"
                }
                steps {
                    addBadge(text: "octopus", icon: "/userContent/octopus_16x16.png", id: "octopus", link: "${octopusURL}/app#/Spaces-3/projects/${jobName}/deployments/releases/${releaseversion}")
                    sh """
                        octo create-release  $hostargs --defaultpackageversion=${packageVersion}
                        octo deploy-release $hostargs --deployto=${deployTo} --waitfordeployment --deploymentTimeout=00:20:00
                    """
                }
            }

        }
    }
}