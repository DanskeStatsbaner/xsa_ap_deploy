import os, subprocess, json, traceback, re, yaml
from time import sleep

sleep(300)

environment = get_octopusvariable("Octopus.Environment.Name")

projectName = get_octopusvariable("Octopus.Project.Name")
releaseNumber = get_octopusvariable("Octopus.Release.Number")
containerName = f"dataArt.{projectName}.{releaseNumber}.{environment}"

XSAurl = get_octopusvariable("dataART.XSAUrl")
XSAuser = get_octopusvariable("dataART.XSAUser")
XSAspace = get_octopusvariable("dataART.XSASpace")

print(environment, projectName, releaseNumber, releaseNumber, containerName, XSAurl, XSAuser, XSAspace)

print('Testing')

printwarning('Tester')