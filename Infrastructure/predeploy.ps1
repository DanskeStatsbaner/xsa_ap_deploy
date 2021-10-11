$environment = $OctopusParameters["Octopus.Environment.Name"]

# exit if environment is Sandbox (sit)
if($environment -eq "sit") { Exit }

write-host "*******************************************************************"
write-host " START predeploy.ps1"
write-host "*******************************************************************"

###############################################################################
# Get all relevant parameters from octopus (variable set dataART)
###############################################################################

$XSAPW = $args[0]

$projectName = $OctopusParameters["Octopus.Project.Name"]
$releaseNumber = $OctopusParameters["Octopus.Release.Number"]
$containerName = "dataArt.$($projectName).$($releaseNumber).$($environment)"

$XSAurl = $OctopusParameters["dataART.XSAUrl"]
$XSAuser = $OctopusParameters["dataART.XSAUser"]
$XSAspace = $OctopusParameters["dataART.XSASpace"]

$HANAHost = $OctopusParameters["dataART.Host"]
$HANAInstance = $OctopusParameters["dataART.Instance"]
$HANADatabase = $OctopusParameters["dataART.Database"]

###############################################################################
# Get SQL from project
###############################################################################

write-host "*** Get SQL from project"

$workdirPath = $pwd.ToString()
$workdirPath = $workdirPath.Substring(2, $workdirPath.IndexOf("\Deployment")-2)

$fullPath = "$($workdirPath)\Deployment\PreDeploy\$($environment)\*.txt"
if (Test-Path c:$($fullPath)) {}
else
{
   write-host "*******************************************************************"
   write-host " STOP predeploy.ps1 - no pre-deploy SQL defined"
   write-host "*******************************************************************"
   Exit
}

$files = Get-ChildItem -Path c:$($fullPath) | sort $files.FullName

$arrFiles = @();

foreach($file in $files ) 
{
    $fileContent = Get-Content $file.FullName
    $allLines = [string]::join(" ",($fileContent.Split("`n")))
    $allLines = [string]::join(" ",($allLines.Split("`r")))
    $arrFiles += $allLines;
}

$allLines = [string]::join(" ", $arrFiles)

if ($allLines -eq ' ')
{
   write-host "*******************************************************************"
   write-host " STOP predeploy.ps1 - no pre-deploy SQL defined"
   write-host "*******************************************************************"
   Exit
}

###############################################################################
# Get the XSA servicename for the project from the mta.yaml file
###############################################################################

write-host "*** Get MTA information for $projectName"

if (Test-Path c:\Octopus\Work\$($containerName)-serviceName.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceName.txt }

docker exec -it $containerName /bin/sh -c "xs login -u $XSAuser -p $XSAPW -a $XSAurl -o orgname -s $XSAspace && xs mta $projectName > /data/$($containerName)-serviceName.txt"

$File = Get-Content c:\Octopus\Work\$($containerName)-serviceName.txt

foreach ($line in $File)
{
    $Arr = $line -split ' '
    foreach ($cell in $Arr)
    {
        if ($cell -eq 'hdi-shared'){$serviceName = $Arr[0]}
    }
}

###############################################################################
# Create new service key and get credentials
###############################################################################

$serviceKey = $($serviceName) + "-sk"

write-host "*** Setup servicekey $serviceKey"

if (Test-Path c:\Octopus\Work\$($containerName)-serviceKey.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceKey.txt }

docker exec -it $containerName /bin/sh -c "xs login -u $XSAuser -p $XSAPW -a $XSAurl -o orgname -s $XSAspace && xs delete-service-key $serviceName $serviceKey -f && xs create-service-key $serviceName $serviceKey && xs service-key $serviceName $serviceKey > /data/$($containerName)-serviceKey.txt"

$File = Get-Content c:\Octopus\Work\$($containerName)-serviceKey.txt

foreach ($line in $File)
{
    $Arr = $line -split ' '
    foreach ($cell in $Arr)
    {
        if ($cell -eq '"user"'){$userArr = $Arr[4] -split '"'}
        elseif ($cell -eq '"password"'){$passwordArr = $Arr[4] -split '"'}
    }
}

$DBuser = $userArr[1]
$DBpw = $passwordArr[1]

if ($DBuser -eq ' ')
{
   write-host "*******************************************************************"
   write-host " STOP predeploy.ps1 - no HDI service key found"
   write-host "*******************************************************************"
   Exit
}

###############################################################################
# Get SQL from project and execute
###############################################################################

write-host "*** Run pre-deployment SQL"

if (Test-Path c:\Octopus\Work\$($containerName)-SQLoutput.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoutput.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoneLine.txt }
Set-Content c:\Octopus\Work\$($containerName)-SQLoneLine.txt -value $allLines 

docker exec -it $containerName /bin/sh -c "hdbsql -n $HANAHost -i $HANAInstance -d $HANADatabase -u $DBuser -p $DBpw -quiet -a -I /data/$($containerName)-SQLoneLine.txt -O /data/$($containerName)-SQLoutput.txt"

###############################################################################
# Analyse SQL result
###############################################################################

$fileContent = Get-Content c:\Octopus\Work\$($containerName)-SQLoutput.txt

$fileContentArr = $fileContent.Split(@("`r`n", "`r", "`n"),[StringSplitOptions]::None)

Write-Host "SQL results:"
Write-Host " "

$resultCode = 0

ForEach($fileLine in $fileContentArr) 
{
    Write-Host $fileLine
    $lineContentArr = $fileLine.Split(" ",[StringSplitOptions]::None)
    $resultCode += $lineContentArr[1]
}

###############################################################################
# Cleanup - delete servicekey and delete files
###############################################################################

write-host "*** Cleanup - delete servicekey"

docker exec -it $containerName /bin/sh -c "xs login -u $XSAuser -p $XSAPW -a $XSAurl -o orgname -s $XSAspace && xs delete-service-key $serviceName $serviceKey -f"

if (Test-Path c:\Octopus\Work\$($containerName)-serviceName.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceName.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-serviceKey.txt) { Remove-Item c:\Octopus\Work\$($containerName)-serviceKey.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoutput.txt }
if (Test-Path c:\Octopus\Work\$($containerName)-SQLoneLine.txt) { Remove-Item c:\Octopus\Work\$($containerName)-SQLoneLine.txt }

write-host "*******************************************************************"
write-host " STOP predeploy.ps1"
write-host "*******************************************************************"

Exit $resultCode