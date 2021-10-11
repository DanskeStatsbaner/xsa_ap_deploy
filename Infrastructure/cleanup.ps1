$environment = $OctopusParameters["Octopus.Environment.Name"]

# exit if environment is Sandbox (sit)
if($environment -eq "sit") { Exit }

write-host "*******************************************************************"
write-host " START cleanup.ps1"
write-host "*******************************************************************"

###############################################################################
# Get all relevant parameters from octopus (variable set dataART)
###############################################################################

$projectName = $OctopusParameters["Octopus.Project.Name"]
$releaseNumber = $OctopusParameters["Octopus.Release.Number"]
$containerName = "dataArt.$($projectName).$($releaseNumber).$($environment)"

###############################################################################
# Stop and delete containers
###############################################################################

if ($(docker container ls -aq -f name="$containerName").length -gt 0){ docker container stop $($containerName) }
docker container prune -f

###############################################################################
# Delete workfiles
###############################################################################

if (Test-Path c:\Octopus\Work\$($containerName)-SQLoutput.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoutput.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoneLine.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-serviceName.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceName.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-serviceKey.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceKey.txt }
if (Test-Path c:\Octopus\Work\$($containerName).mtar) { Remove-Item c:\Octopus\Work\$($containerName).mtar }

write-host "*******************************************************************"
write-host " STOP cleanup.ps1"
write-host "*******************************************************************"