$TempDir = "$env:SystemDrive\TEMP"

## Set TLS versions
[Net.ServicePointManager]::SecurityProtocol = "tls12, tls11, tls"

## Check Python
$PythonExists = $false
$NodePath = $env:Path.Split(";")
$NodePath | ForEach-Object { if ($_.Contains("Python")){ $PythonExists = $true; Write-Debug "Python is already installed"; break }}
if (-not $PythonExists){
    $PyVersion = "3.6.5" # 3.7.0 is still beta
    $PyInstaller = "python-$PyVersion-amd64.exe"
    #$ChkAlgo = "MD5"
    #$PyChecksum = "9E96C934F5D16399F860812B4AC7002B"
    $ChkAlgo = "SHA1"
    $PyChecksum = "453A4445A3DC8F295F637CAD51B69D233D4089BA"
    if (![System.IO.File]::Exists("$TempDir\$PyInstaller") -or (Get-FileHash $TempDir\$PyInstaller -Algorithm $ChkAlgo).Hash -ne $PyChecksum){
        Write-Output "Downloading Python version $PyVersion"
        Invoke-WebRequest https://www.python.org/ftp/python/$PyVersion/$PyInstaller -OutFile $TempDir\$PyInstaller -ErrorAction Stop
    } else { Write-Output "Python installer exists. Using this." }
    $Process2 = Start-Process $PSHome\Powershell.exe -WorkingDirectory $PSHOME -ArgumentList "$TempDir\$PyInstaller /passive PrependPath=1 Include_doc=0 InstallLauncherAllUsers=0 SimpleInstall=1 SimpleInstallDescription=`"WoT Node Setup currently running for Python. Please wait...`"" -NoNewWindow -PassThru -Wait -ErrorAction Stop
    #Invoke-Expression "& $TempDir\$PyInstaller /passive PrependPath=1 Include_doc=0 InstallLauncherAllUsers=0 SimpleInstall=1 SimpleInstallDescription=`"WoT Node Setup currently running for Python. Please wait...`""
    #Write-Debug "Removing Python installer"
    # Keep cached for later use
    #Remove-Item $TempDir\$PyInstaller
}

## "Refresh" the PATH variable to find Python and scripts
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

## Setup virtualenv
pip install --user virtualenv
Push-Location $env:USERPROFILE
virtualenv wottracker
source wottracker\bin\

## Install Python modules
Invoke-WebRequest https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/requirements.txt -OutFile requirements.txt
pip install -r requirements.txt

## Download tracker node files
Invoke-WebRequest https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/trackerv2/client/node.py -OutFile node.py

# Return to original location
Pop-Location