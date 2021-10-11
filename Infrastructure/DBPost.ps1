$environment = $OctopusParameters["Octopus.Environment.Name"]

# exit if environment is not production (prd)
if($environment -ne "prd") { Exit }

write-host "*******************************************************************"
write-host " START DBPost.ps1"
write-host "*******************************************************************"

###############################################################################
# Get all relevant parameters from octopus (variable set dataART)
###############################################################################

$DBpw = $args[0]
$DBuser = $OctopusParameters["dataART.DBUser"]

$workdirPath = $(pwd)
$projectName = $OctopusParameters["Octopus.Project.Name"]
$releaseNumber = $OctopusParameters["Octopus.Release.Number"]
$containerName = "dataArt.$($projectName).$($releaseNumber).$($environment)"

$XSAurl = $OctopusParameters["dataART.XSAUrl"]
$XSAuser = $OctopusParameters["dataART.XSAUser"]
$XSAspace = $OctopusParameters["dataART.XSASpace"]

$HANAHost = $OctopusParameters["dataART.Host"]
$HANAInstance = $OctopusParameters["dataART.Instance"]
$HANADatabase = $OctopusParameters["dataART.Database"]

$HANADeployCounter = $OctopusParameters["dataART.DeployCounter"]
$HANADeployCounter = $HANADeployCounter - 1
Set-OctopusVariable -name "dataART.DeployCounter" -value "$HANADeployCounter"

if ($HANADeployCounter -ne 0) 
{ 
	write-host "*******************************************************************"
	write-host " STOP DBPost.ps1"
	write-host "*******************************************************************"
	Exit
}


###############################################################################
# Execute prepare SQL
###############################################################################

write-host "*** Run DB prepare SQL"

$allLines = 'CALL "SYSTEM"."REVOKE_REMOTE_SOURCE_ACCESS"(EX_MESSAGE => ?);'

if (Test-Path c:\Octopus\Work\$($containerName)-SQLoutput.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoutput.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoneLine.txt }
Set-Content c:\Octopus\Work\$($containerName)-SQLoneLine.txt -value $allLines 

docker exec -it $containerName /bin/sh -c "hdbsql -n $HANAHost -i $HANAInstance -d $HANADatabase -u $DBuser -p $DBpw -quiet -a -I /data/$($containerName)-SQLoneLine.txt -O /data/$($containerName)-SQLoutput.txt"

###############################################################################
# Cleanup - delete files
###############################################################################

if (Test-Path c:\octopus\work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\octopus\work\$($containerName)-SQLoutput.txt }
if (Test-Path c:\octopus\work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\octopus\work\$($containerName)-SQLoneLine.txt }

write-host "*******************************************************************"
write-host " STOP DBPost.ps1"
write-host "*******************************************************************"