from ipaddress import IPv4Address, IPv4Network
from multiping import MultiPing
import itertools, sys, asyncio
import click


def _get_ranges_expanded(octets):
    parsed_ranges = (tuple(map(int, sorted(octet.split('-')))) for octet in octets)
    ranges = [range(r[0], r[-1] + 1) if len(r) > 1 else r for r in parsed_ranges]
    ranges_expanded = ['.'.join(map(str, x)) for x in itertools.product(*ranges)]
    
    return ranges_expanded


def _get_ips_to_ping(networks_input):
    # in the tuple of IPs returned, anything ending in .0 or .1 will not be included
    zero_and_one = {'0','1'}
    any_invalid = False
    list_to_ping = []

    for scope in networks_input:
        invalid = False
        scope = scope.strip()
        octets = scope.split('.')
        first_3_octets = octets[:3]


        if len(octets) != 4 or any('/' in x for x in first_3_octets):
            invalid = True

        
        elif all(x in scope for x in ('-','/') ):
            last_octet = octets[3]
            ranges_expanded = _get_ranges_expanded(first_3_octets)

            networks = [IPv4Network( '.'.join((x, last_octet)) , strict=False) for x in ranges_expanded]
            addresses = [z for y in networks for x in y if (z:=str(x)).split('.')[-1] not in zero_and_one]

        elif '-' in scope:
            ranges_expanded = _get_ranges_expanded(octets)
            addresses = [x for x in ranges_expanded if x.split('.')[-1] not in zero_and_one]

        elif '/' in octets[-1]:
            try:
                network = IPv4Network(scope, strict=False)
            except:
                invalid = True
            else:
                addresses = [z for x in network if (z:=str(x)).split('.')[-1] not in zero_and_one]

        elif octets[-1] not in zero_and_one:
            addresses = (scope,)
            
        else:
            invalid = True

        
        if invalid:
            if ',' in scope:
                click.echo("\nCommas should not be used to separate IP scopes, use spaces instead.")
            else:
                click.echo()
            click.echo(f"Entry of '{scope}' is invalid. Skipping this entry.")
            any_invalid = True
            continue

        checked_addresses = []
        for address in addresses:
            try:
                IPv4Address(address)
            except:
                click.echo(f"Entry of '{address}' is invalid. Skipping this entry.")
                invalid = True
                continue
            checked_addresses.append(address)

        list_to_ping.extend(checked_addresses)

    return (*list_to_ping,), any_invalid



def find_alive_hosts(networks_input, verbose):
    ips_to_ping_full, invalid = _get_ips_to_ping(networks_input)

    if invalid:
        click.echo()

    if not ips_to_ping_full:
        click.echo('No valid IPv4 addresses or networks entered. Quitting.')
        sys.exit()

    click.echo('\nPinging addresses...')

    ping = MultiPing(ips_to_ping_full)
    ping.send()
    responses_1, timeouts_1 = ping.receive(0.5)
    responses = responses_1.copy()

    if verbose and responses_1:
        click.echo(f"\nIPs responded to first ping:\n{', '.join([x for x in responses_1])}\n")

    if len(ips_to_ping_full) > len(responses_1):
        ping.send()
        responses_2, timeouts_2 = ping.receive(5)
        responses.update(responses_2)

        if verbose and responses_2:
            click.echo(f"\nIPs responded to second ping:\n{[x for x in responses_2]}\n")

    hosts_alive = sorted(responses.keys(), key=lambda x: IPv4Address(x))
    
    click.echo(f"{len(hosts_alive)} hosts responded to ping.\n")
    
    return (*hosts_alive,)



async def _check_ssh_open(ip, verbose):    
    try:
        conn = asyncio.open_connection(f'{ip}', 22)
        reader, writer = await asyncio.wait_for(conn, timeout=1.5)
        writer.close()
        await writer.wait_closed()
        return ip
    except (asyncio.exceptions.TimeoutError, ConnectionRefusedError):
        try:
            conn = asyncio.open_connection(f'{ip}', 22)
            reader, writer = await asyncio.wait_for(conn, timeout=8)
            writer.close()
            await writer.wait_closed()
            return ip
        except (asyncio.exceptions.TimeoutError, ConnectionRefusedError):
            conn.close()
            return


async def _check_ssh_open_sem(ip, verbose, sem):
    async with sem:
        return await _check_ssh_open(ip, verbose)


async def _do_check_ssh_tasks(alive_hosts, verbose):

    click.echo('\n\nScanning for port 22...')

    if len(alive_hosts) > 255:
        sem = asyncio.Semaphore(255)
        tasks = [_check_ssh_open_sem(ip, verbose, sem) for ip in alive_hosts]
    else:
        tasks = [_check_ssh_open(ip, verbose) for ip in alive_hosts]

    results = []
    with click.progressbar(asyncio.as_completed(tasks), length=len(tasks)) as pbar:
        for coro in pbar:
            result = await coro
            if result:
                results.append(result)

    ssh_open_ips = (*results,)
    
    click.echo(f"{len(ssh_open_ips)} hosts have port 22 open.\n")

    if verbose:
        click.echo(f"{', '.join(ssh_open_ips)}\n")
    
    return ssh_open_ips



async def find_ssh_open(networks_input, verbose):
    alive_hosts = find_alive_hosts(networks_input, verbose)
    hosts_open_ssh = await _do_check_ssh_tasks(alive_hosts, verbose)

    #if len(alive_hosts) > len(hosts_open_ssh):
     #   alive_hosts_closed_ssh = sorted( list(set(alive_hosts) - set(hosts_open_ssh)),
      #                            key=lambda x: IPv4Address(x))
    
    return hosts_open_ssh


if __name__ == '__main__':
    #find_ssh_open()
    networks_input = input('Enter IPs to ping. Enter CIDR or a range with a dash ("-"), separated by commas.: ')
    print(_get_ips_to_ping(networks_input))
