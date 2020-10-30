from discovery_functions.find_alive_hosts import find_alive_hosts, find_ssh_open
from discovery_functions.check_radio_ssh import check_radio_ssh
from random import randint
import asyncio, re
import asyncssh, aioping, click



async def _ensure_snmp_settings(conn):
    snmp_output = await conn.run("cat /tmp/system.cfg | grep -n snmp", timeout=15)
    snmp_to_add = ['location', 'contact', 'community']

    if snmp_output.stdout:
        line_num = snmp_output.stdout[:6].split(':')[0]
        snmp_check = snmp_output.stdout.rstrip().split('\n')
        snmp_status = {k.split('.')[1]:v for k,v in [s.split('=') for s in snmp_check]}

        for feature, field in snmp_status.items():

            if feature == 'status':
                if field == 'disabled':
                    await conn.run("sed -i 's/^snmp.status=disabled/snmp.status=enabled/' /tmp/system.cfg", check=True, timeout=15)

            elif field == 'REDACTED':
                snmp_to_add.remove(feature)

            elif field != 'REDACTED':
                snmp_to_add.remove(feature)
                await conn.run(f"sed -i 's/^snmp.{feature}={field}/snmp.{feature}=REDACTED/' /tmp/system.cfg", check=True, timeout=15)

        for feature in snmp_to_add:
            await conn.run(f"sed -i '{line_num} i snmp.{feature}=REDACTED' /tmp/system.cfg", check=True, timeout=15)

    else:
        await conn.run("sed -i 's/^snmp.status=disabled/snmp.status=enabled/' /tmp/system.cfg", check=True, timeout=15)
        
        for feature in snmp_to_add:
            await conn.run(f'echo "snmp.{feature}=REDACTED" >> /tmp/system.cfg', check=True, timeout=15)



async def _ensure_ntp_client(conn, ntp_server_validate):
    ntp_output = await conn.run("cat /tmp/system.cfg | grep ntp", timeout=15)
            
    if ntp_output.stdout:
        ntp_check = ntp_output.stdout.rstrip().split('\n')
        ntp_status = [(k,v) for k,v in [s.split('=') for s in ntp_check]]

        for feature, field in ntp_status:
            if 'ntpclient' in feature and field == 'disabled':
                await conn.run(f"sed -i 's/^{feature}=disabled/{feature}=enabled/' /tmp/system.cfg", check=True, timeout=15)

            elif feature == 'ntpclient.1.server' and not ntp_server_validate.match(field):
                await conn.run(f"sed -i 's/^ntpclient.1.server={field}/ntpclient.1.server={randint(0,3)}.ubnt.pool.ntp.org/' /tmp/system.cfg", check=True, timeout=15)        

    else:
        await conn.run('echo "ntpclient.status=enabled" >> /tmp/system.cfg', check=True, timeout=15)
        await conn.run('echo "ntpclient.1.status=enabled" >> /tmp/system.cfg', check=True, timeout=15)
        await conn.run(f'echo "ntpclient.1.server={randint(0,3)}.ubnt.pool.ntp.org" >> /tmp/system.cfg', check=True, timeout=15)



async def _do_ssh_commands(conn, device_info, ntp_server_validate, flags):

    wds, snmp, ntp, traffic_shaper, timezone_, ff_reporting_mode = flags
    
    if wds:
        if device_info.is_airrouter:
            await conn.run("sed -i 's/^wireless.1.wds.status=enabled/wireless.1.wds.status=disabled/' /tmp/system.cfg", check=True, timeout=15)
        
        else:   
            await conn.run("sed -i 's/^wireless.1.wds.status=disabled/wireless.1.wds.status=enabled/' /tmp/system.cfg", check=True, timeout=15)
    

    if ff_reporting_mode and device_info.is_rocket and not device_info.is_legacy:
        await conn.run("sed -i 's/^radio.1.ff_cap_rep=0/radio.1.ff_cap_rep=1/' /tmp/system.cfg", check=True, timeout=15)

    if timezone_:
        await conn.run("sed -i 's/^system.timezone=.*/system.timezone=REDACTED/' /tmp/system.cfg", check=True, timeout=15)
    
    if traffic_shaper:
        await conn.run("sed -i 's/^tshaper.status=enabled/tshaper.status=disabled/' /tmp/system.cfg", check=True, timeout=15)
    
    if ntp:
        await _ensure_ntp_client(conn, ntp_server_validate)
    
    if snmp:
        await _ensure_snmp_settings(conn)

    await conn.run("save", timeout=20)
    await asyncio.sleep(2)
    
    try:
        await conn.run("restart", timeout=15)

    except asyncssh.process.TimeoutError:
        await asyncio.sleep(30)
        
        try:
            await conn.run("restart", timeout=20)

        except asyncssh.process.TimeoutError:
            save_config = False

        else:
            save_config = True

    else:
        save_config = True

    return save_config



async def _run_ssh_commands(device_info, ntp_server_validate, flags, verbose):
    ip = device_info.ip

    if device_info.altpass:
        async with asyncssh.connect(host=ip, username=REDACTED, password=REDACTED, known_hosts=None) as conn:
            try:
                save_config = await _do_ssh_commands(conn, device_info, ntp_server_validate, flags)
            except Exception as e:
                return (ip, False, e)

    else:
        async with asyncssh.connect(host=ip, username=REDACTED, password=REDACTED, known_hosts=None) as conn:
            save_config = await _do_ssh_commands(conn, device_info, ntp_server_validate, flags)


    if not save_config:
        #if verbose:
         #   click.echo(f"Save command timed out for {ip}")
        return (ip, False, 'Save command timed out')

    await asyncio.sleep(15)
    
    try:
        latency = await aioping.ping(ip) * 1000
        #if verbose:
         #   click.echo(f"{ip} responded in {round(latency, 2)} ms")
        still_up = True

    except TimeoutError:
        await asyncio.sleep(10)
        try:
            latency = await aioping.ping(ip) * 1000
        
        except TimeoutError:
            await asyncio.sleep(90)
            try:
                latency = await aioping.ping(ip) * 1000

            except TimeoutError:
                #if verbose:
                 #   click.echo(f"{ip} timed out.")
                still_up = False

            else:
                #if verbose:
                 #   click.echo(f"{ip} responded in {round(latency, 2)} ms (attempt #3)")
                still_up = True

        else:
            #if verbose:
             #   click.echo(f"{ip} responded in {round(latency, 2)} ms (attempt #2)")
            still_up = True

    return (ip, still_up)



async def _run_ssh_commands_sem(sem, device, ntp_server_validate, flags, verbose):
    async with sem:
        return await _run_ssh_commands(device, ntp_server_validate, flags, verbose)



def _ping_only_mode(networks, verbose):
    return find_alive_hosts(networks, verbose)


def _ssh_check_only_mode(networks, verbose):
    devices_ssh_open = asyncio.run( find_ssh_open(networks, verbose) )
    succeeded, *_ = asyncio.run( check_radio_ssh(devices_ssh_open, verbose) )
    return succeeded


async def _configure_mode(cli_options):
    (networks, mode, wds, snmp, ntp, traffic_shaper, 
                timezone_, ff_reporting_mode, verbose) = cli_options
    flags = (wds, snmp, ntp, traffic_shaper, timezone_, ff_reporting_mode)
    del mode

    if not any(flags):
        click.echo('\nYou must enable at least 1 option in configure mode.')
        return

    devices_ssh_open = await find_ssh_open(networks, verbose)
    succeeded, failed, airfiber, maybe_switch = await check_radio_ssh(devices_ssh_open, verbose)

    if not succeeded:
        click.echo('No IPs passed device check, quitting...')
        return

    if airfiber:
        click.echo(f"airFiber ({len(airfiber)} hosts): {', '.join(airfiber)}\n")
    
    if failed:
        click.echo(f"Responded to ping, failed radio check ({len(failed)} hosts): {', '.join(failed)}\n")

        if maybe_switch:
            click.echo(f"Probably switch ({len(maybe_switch)} hosts): {', '.join(maybe_switch)}\n")


    click.echo('\n\nPerforming device cleanup...')
    
    ntp_server_validate = re.compile("[0-3]\.ubnt\.pool\.ntp\.org")

    if len(succeeded) > 255:
        sem = asyncio.Semaphore(255)
        tasks = [_run_ssh_commands_sem(sem, device, ntp_server_validate, flags, verbose) for device in succeeded]
    else:
        tasks = [_run_ssh_commands(device, ntp_server_validate, flags, verbose) for device in succeeded]

    still_up, went_down, exceptions = [], [], []

    with click.progressbar(asyncio.as_completed(tasks), length=len(tasks)) as pbar:
        for coro in pbar:
            x = await coro
            if len(x) == 2:
                if x[1]:
                    still_up.append(x[0])
                else:
                    went_down.append(x[0])

            elif len(x) == 3:
                exceptions.append( (x[0], x[2]) )

            else:
                click.echo('THE FUCK HAPPENED?')
                click.echo(x)

    click.echo(f"Device cleanup complete. {len(still_up)} out of {len(succeeded)} devices still online.")

    if went_down:
        click.echo(f'\nDevices that went offline: {went_down}')

    if exceptions:
        click.echo(f'\nExceptions: {exceptions}')


def device_cleanup(cli_options):
    networks = cli_options.networks
    mode = cli_options.mode
    verbose = cli_options.verbose
    
    if mode == 'configure':
        asyncio.run(_configure_mode(cli_options))
    
    elif mode == 'ping-only':
        successful = _ping_only_mode(networks, verbose)
        if not verbose:
            click.echo(f"Hosts Alive: {', '.join([x for x in successful])}")
    
    elif mode == 'ssh-check-only':
        successful = _ssh_check_only_mode(networks, verbose)
        if not verbose:
            click.echo(f"Hosts with port 22 open that are valid radios: {', '.join([x.ip for x in successful])}")


if __name__ == '__main__':
    networks = '10.0.0.0/24'
    verbose = True
    _configure_mode(networks, 'configure', True, True, True, True, True, 
                                True, verbose)