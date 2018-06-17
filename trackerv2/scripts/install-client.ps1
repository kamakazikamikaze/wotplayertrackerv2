#Requires -RunAsAdministrator

Function Get-RandomPassword() {
    Param(
        [int]$length=14,
        [string[]]$charset
    )

    For ($loop=1; $loop -le $length; $loop++){
        $TempPassword+=($charset | Get-Random)
    }

    return $TempPassword
}

$Hostname = $env:COMPUTERNAME
$NodeAccount = "wotnode"
$FirewallRule = "WoT Tracker Access"
$AccountDescription = "WoT Tracker Node Account"
$HomeDir = "$env:SystemDrive\Users\$NodeAccount"
$PathOutFile = "wotnodepath.txt"
$TempDir = "$env:SystemDrive\TEMP"

$PassChar = $NULL;For ($c=33;$c -le 126; $c++) {$PassChar+=,[char][byte]$c}

$Password = Get-RandomPassword -charset $PassChar

## Create user
if ($PSVersionTable.PSVersion.Major -ge 5 -and $PSVersionTable.PSVersion.MajorRevision -ge 1){
    New-LocalUser $NodeAccount -Description $AccountDescription -Password $Password -PasswordNeverExpires
    $NewUser = [adsi]"WinNT://$Hostname/$NodeAccount,user"
    $NewUser.Put("HomeDirectory", $HomeDir)
    $NewUser.SetInfo()
} else {

    $ADSIComp = [adsi]"WinNT://$Hostname"
    $NewUser = $ADSIComp.Create('User',$NodeAccount)
    $NewUser.SetPassword($Password)
    $NewUser.Put("description", $AccountDescription)
    $NewUser.Put("HomeDirectory", $HomeDir)
    $NewUser.userflags = 0x100000 # Don't expire password
    $NewUser.SetInfo()
}

## Login and get PATH
$seclogon = Get-Service -Name seclogon
if ($seclogon.StartType -eq "Disabled"){Set-Service -Name seclogon -Computer $Hostname -StartupType Manual}
if ($seclogon.Status -ne "Running"){$seclogon.Start()}

$NodeCred = New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList $NodeAccount,(ConvertTo-SecureString -AsPlainText $Password -Force)
Start-Process $PSHOME\powershell.exe -WorkingDirectory $PSHOME -Credential $NodeCred -ArgumentList "-Command `$env:Path" -NoNewWindow -PassThru -Wait -RedirectStandardOutput $PathOutFile

## Check Python
$PythonExists = $false
$NodePath = (Get-Content $PathOutFile).Split(";")
Remove-Item $PathOutFile
$NodePath | ForEach-Object {if ($_.Contains("Python")) {$PythonExists = $true; break}}
if (-not $PythonExists){
    [Net.ServicePointManager]::SecurityProtocol = "tls12, tls11, tls"
    $PyVersion = "3.6.5" # 3.7.0 is still beta
    $PyInstaller = "python-$PyVersion-amd64.exe"
    Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/$PyInstaller" -OutFile "$TempDir\$PyInstaller"
    Start-Process $PSHome\Powershell.exe -WorkingDirectory $PSHOME -Credential $NodeCred -ArgumentList "$TempDir\$PyInstaller /passive PrependPath=1 Include_doc=0 InstallLauncherAllUsers=0 SimpleInstall=1 SimpleInstallDescription=`"WoT Node Setup currently running for Python. Please wait...`"" -NoNewWindow -PassThru -Wait
    Remove-Item $TempDir\$PyInstaller
}
## Add scheduler task for running node

## Add Firewall exception

## Output installation summary to .ini or .json file somewhere

$jsonResults = [pscustomobject]@{
    username = $NodeAccount
    python = $false
    home = $HomeDir
}


$jsonResults | ConvertTo-Json -Depth 10 | Out-File "installresults.json"