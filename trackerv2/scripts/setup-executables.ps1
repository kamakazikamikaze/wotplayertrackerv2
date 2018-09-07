[CmdletBinding()]
Param(
	[Parameter(Mandatory=$True)][ValidateSet("server","client")][String]$installing
)

$TempDir = "$env:SystemDrive\TEMP"
$HomeDir = "$env:USERPROFILE"

## Set TLS versions
[Net.ServicePointManager]::SecurityProtocol = "tls12, tls11, tls"

If ($installing -eq "server"){
	Invoke-WebRequest https://github.com/git-for-windows/git/releases/download/v2.18.0.windows.1/Git-2.18.0-64-bit.exe -OutFile "Git-2.18.0-64-bit.exe"
	./Git-2.18.0-64-bit.exe /VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS /COMPONENTS=""
}

## Check Python
$PythonExists = $false
$PythonPath = $null
$env:Path.Split(";") | ForEach-Object {
	if ($_.Contains("Python") -and ($(& "$_\python" -V 2>$null).Substring(0,10) -eq "Python 3.7")){
		$PythonExists = $true
		$PythonPath = "$_"
		Write-Debug "Python is already installed"
		break
	}
}
if (-not $PythonExists){
    $PyVersion = "3.7.0"
    $PyInstaller = "python-$PyVersion-amd64.exe"
    $ChkAlgo = "SHA1"
    $PyChecksum = "FE8A2F2B59DB38073AD2F8EBC3372841830CD2DB"
    if (![System.IO.File]::Exists("$TempDir\$PyInstaller") -or (Get-FileHash $TempDir\$PyInstaller -Algorithm $ChkAlgo).Hash -ne $PyChecksum){
        Write-Output "Downloading Python version $PyVersion"
        Invoke-WebRequest https://www.python.org/ftp/python/$PyVersion/$PyInstaller -OutFile $TempDir\$PyInstaller -ErrorAction Stop
    } else { Write-Output "Python installer exists. Using this." }
    $Process2 = Start-Process $PSHome\Powershell.exe -WorkingDirectory $PSHOME -ArgumentList "$TempDir\$PyInstaller /passive PrependPath=1 Include_doc=0 InstallLauncherAllUsers=0 SimpleInstall=1 SimpleInstallDescription=`"WoT Node Setup currently running for Python. Please wait...`"" -NoNewWindow -PassThru -Wait -ErrorAction Stop
    #Invoke-Expression "& $TempDir\$PyInstaller /passive PrependPath=1 Include_doc=0 InstallLauncherAllUsers=0 SimpleInstall=1 SimpleInstallDescription=`"WoT Node Setup currently running for Python. Please wait...`""
    #Write-Debug "Removing Python installer"
    # Keep cached for later use
    #Remove-Item $TempDir\$PyInstaller
	## "Refresh" the PATH variable to find Python and scripts
	$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
	$env:Path.Split(";") | ForEach-Object {
		if ($_.Contains("Python") -and ($(& "$_\python" -V 2>$null).Substring(0,10) -eq "Python 3.7")){
			$PythonPath = $_
			break
		}
	}
}

## Setup virtualenv
Push-Location $HomeDir
& "$PythonPath\Scripts\python.exe" -m venv wottracker

## Install Python modules
Invoke-WebRequest https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/$installing-requirements.txt -OutFile requirements.txt
& "$HomeDir\wottracker\Scripts\pip.exe" install -r requirements.txt

If ($installing -eq "server") {
	git clone https://github.com/kamakazikamikaze/wotplayertrackerv2.git
	New-Item -Path wotplayertrackerv2\config -ItemType directory
	cd wotplayertrackerv2\trackerv2\server
	& "$HomeDir\wottracker\Scripts\python.exe server.py ..\..\config\server.json -c ..\..\config\client.json -g"
} Else {
	## Download tracker node update file
	Invoke-WebRequest https://github.com/kamakazikamikaze/wotplayertrackerv2/raw/master/trackerv2/client/node.py -OutFile update.py
	$jsonClient = [pscustomobject]@{
		server = "http://changeme/"
		application_id = "demo"
		throttle = 10
		debug = False
	}

	$jsonClient | ConvertTo-Json -Depth 10 | Out-File $client.json
}

# Return to original location
Pop-Location
