$environment = $OctopusParameters["Octopus.Environment.Name"]

# exit if environment is Sandbox (sit)
if($environment -eq "sit") { Exit }

write-host "*******************************************************************"
write-host " START deploy.ps1"
write-host "*******************************************************************"

###############################################################################
# Get all relevant parameters from octopus (variable set dataART)
###############################################################################

$XSAPW = $args[0]

$workdirPath = $pwd.ToString()
$workdirPath = $workdirPath.Substring(0, $workdirPath.IndexOf("\Deployment"))

$projectName = $OctopusParameters["Octopus.Project.Name"]
$releaseNumber = $OctopusParameters["Octopus.Release.Number"]
$containerName = "dataArt.$($projectName).$($releaseNumber).$($environment)"

$XSAurl = $OctopusParameters["dataART.XSAUrl"]
$XSAuser = $OctopusParameters["dataART.XSAUser"]
$XSAspace = $OctopusParameters["dataART.XSASpace"]

###############################################################################
# Copy project mtar file to work directory - c:\octopus\work\
###############################################################################

if (Test-Path c:\Octopus\Work\$($containerName).mtar) { Remove-Item c:\Octopus\Work\$($containerName).mtar }
Copy-Item "$workdirPath\dataArt.$projectName.$releaseNumber.mtar" -Destination "C:\octopus\work\$containerName.mtar" -Force

###############################################################################
# Deploy:
#
# Docker exec explain: 
# /bin/sh -c  = run shell within container:
#    cp = copy mtar from mount to container root
#    login hana
#    deploy hana
#
###############################################################################

docker exec -it $containerName /bin/sh -c "cp /data/$containerName.mtar . && xs login -u $XSAuser -p $XSAPW -a $XSAurl -o orgname -s $XSAspace && xs deploy -f $containerName.mtar > /data/$containerName.log"

# Get the log and put it into the Octopus log
$FileContent = Get-Content "C:\octopus\work\$containerName.log"

write-host "*******************************************************************"
write-host " Deployment log"
write-host "*******************************************************************"
write-host $FileContent

# Find the log number and create a file with the names of the logs
$Matches = Select-String -InputObject $FileContent -Pattern "xs dmol -i" 
$Start=$Matches.Line.IndexOf("xs dmol -i")
if (-Not $Start.Equals(-1))
{
    $end=$Matches.Line.Substring($Start+12,10).IndexOf("to")
    $logNo=$Matches.Line.Substring($Start+11,$end-1)
}

# Determine if the deploy was as success or a failure
$exitCode = 0
$findErrorStatus = "xs deploy -i " + $logNo + " -a retry"

$Matches = Select-String -InputObject $FileContent -Pattern "$findErrorStatus" 
if ($Matches.LineNumber -gt 0)
{
    $exitCode = 1

    # Download logfiles
    docker exec -it $containerName /bin/sh -c "xs login -u $XSAuser -p $XSAPW -a $XSAurl -o orgname -s $XSAspace && xs dmol -i $logNo"
    $dmolDir = "./mta-op-$logNo"
    docker exec -it $containerName /bin/sh -c "cd $dmolDir . && cat * . "
}

# cleanup
if (Test-Path c:\Octopus\Work\$($containerName).log) { Remove-Item c:\Octopus\Work\$($containerName).log }
if (Test-Path c:\Octopus\Work\$($containerName).txt) { Remove-Item c:\Octopus\Work\$($containerName).txt }

write-host "*******************************************************************"
write-host " STOP deploy.ps1"
write-host "*******************************************************************"

Exit $exitCode