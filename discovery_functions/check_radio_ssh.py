from collections import namedtuple
import asyncio, sys, re
import asyncssh, aioping, click


def _fix_firmware_format(firmware_version):
    firmware_version = firmware_version.split('.',5)[:5]
    del firmware_version[1]
    firmware_version = '.'.join(firmware_version)
    return firmware_version


async def _radio_discovery(ip, radio_discovery_arguments):    
    radio_validate, rocket_validate, legacy_types, ssh_namedtuples = radio_discovery_arguments
    ssh_fail_namedtuple, ssh_succeed_namedtuple = ssh_namedtuples
    
    altpass = can_ssh = is_valid_radio = is_airrouter = is_rocket = is_airfiber = False
    device_name = firmware_version = mac = is_legacy = None
    
    try:
        async with asyncssh.connect(host=ip, username=REDACTED, password=REDACTED, known_hosts=None) as conn:
            mca_status = await conn.run("mca-status | head -n 1", check=True, timeout=7)

    except asyncssh.misc.PermissionDenied:
        try:
            async with asyncssh.connect(host=ip, username=REDACTED, password=REDACTED, known_hosts=None) as conn:
                mca_status = await conn.run("mca-status | head -n 1", check=True, timeout=7)

        except asyncssh.misc.PermissionDenied:
            reason = 'invalid credentials'

        except asyncssh.process.TimeoutError:
            reason = 'connection timeout'

        else:
            can_ssh = True
            altpass = True

    except asyncssh.process.TimeoutError:
        reason = 'connection timeout'

    else:
        can_ssh = True

    if not can_ssh:
        return ssh_fail_namedtuple(ip, can_ssh, reason)

    mca_status_stdout = mca_status.stdout.strip()
    radio_check = radio_validate.match(mca_status_stdout)

    if radio_check:
        is_valid_radio = True
        device_info = {y[0]:y[1] for y in [x.split('=') for x in mca_status_stdout.split(',')]}
        del device_info['deviceIp']
        device_name = device_info.pop('deviceName')
        firmware_version = _fix_firmware_format(device_info.pop('firmwareVersion'))
        mac = device_info.pop('deviceId')
        
        platform = device_info.pop('platform')
        if 'AirRouter' in platform:
            is_airrouter = True

        rocket_check = rocket_validate.match(platform)
        if rocket_check:
            is_rocket = True
        
        radio_type = firmware_version.split('.',1)[0]
        if radio_type in legacy_types:
            is_legacy = True
        else:
            is_legacy = False                
                           
        
    elif 'airFiber' in mca_status_stdout:
        is_airfiber = True

    return ssh_succeed_namedtuple(ip, altpass, can_ssh, is_valid_radio, device_name,
                                    firmware_version, mac, is_airrouter,  
                                    is_rocket, is_legacy, is_airfiber)
    


async def _radio_discovery_sem(sem, ip, radio_discovery_arguments):
    async with sem:
        return await _radio_discovery(ip, radio_discovery_arguments)


async def check_radio_ssh(hosts, verbose):

    click.echo('\n\nChecking IPs for valid radios...')

    radio_validate = re.compile("deviceName=.+,deviceId=..:..:..:..:..:..,firmwareVersion=2?[WX][ACMW].+,platform=.+,deviceIp=.+")
    rocket_validate = re.compile("Rocket.*")
    legacy_types = {'XM','XW'}
    ssh_namedtuples = (
        namedtuple('ssh_fail', ('ip', 'can_ssh', 'reason') ),
        namedtuple('ssh_succeed', ('ip','altpass','can_ssh','is_valid_radio','device_name',
                                    'firmware_version','mac','is_airrouter',
                                    'is_rocket','is_legacy','is_airfiber') )
    )

    radio_discovery_arguments = (radio_validate, rocket_validate, legacy_types, ssh_namedtuples)

    if len(hosts) > 255:
        sem = asyncio.Semaphore(255)
        tasks = [_radio_discovery_sem(sem, ip, radio_discovery_arguments) for ip in hosts]
    else:
        tasks = [_radio_discovery(ip, radio_discovery_arguments) for ip in hosts]

    succeeded, failed, airfiber, maybe_switch = [], [], [], []
    valid_radio_namedtuple = namedtuple('device', ('ip', 'altpass', 'is_rocket', 'is_legacy', 'is_airrouter') )

    with click.progressbar(asyncio.as_completed(tasks), length=len(tasks)) as pbar:
        for coro in pbar:
            result = await coro
            ip = result.ip

            if result.can_ssh:

                if result.is_valid_radio:

                    device = valid_radio_namedtuple(ip, result.altpass, result.is_rocket, 
                                                    result.is_legacy, result.is_airrouter)
                    succeeded.append(device)

                elif result.is_airfiber:
                    airfiber.append(ip)

                else:
                    failed.append(ip)
                    maybe_switch.append(ip)

            else:
                failed.append(ip)
            
    click.echo(f"{len(succeeded)} hosts are valid radios.\n")

    if verbose:
        click.echo(f"SSH login successful, valid radios: {', '.join([x.ip for x in succeeded])}\n")

    return (*succeeded,), (*failed,), (*airfiber,), (*maybe_switch,)



if __name__ == '__main__':

    hosts = [REDACTED]
    asyncio.run(check_radio_ssh(hosts))