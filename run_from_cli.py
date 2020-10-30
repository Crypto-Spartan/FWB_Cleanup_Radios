from device_cleanup import device_cleanup
from collections import namedtuple
import click

CONTEXT_SETTINGS = {'help_option_names':('-h', '--help')}

command_help = ("This tool is designed for use on Ubiquiti airMAX equipment for Freedom Broadband.\n\n"
                "Enter an IPv4 address, network, or multiple networks separated by spaces. These networks can be in CIDR notation (e.g. 10.0.0.0/24) or range notation. Any octet can be used with the range notation (e.g. 10.0.70-80.0-254). Both notations can be used together, as long as the last octet does not use range notation.\n\n"
                "This script will not make any configuration changes on an airFiber, ToughSwitch, EdgeSwitch, EdgeRouter, or USG. Additionally, this script is unable to login to airCubes since they lack SSH functionality. The radios that will be configured include all customer radios, airRouters, and access point radios.\n\n"
                "All of the flags are optional, it is recommended to use -v with the default device cleanup.\n\n"
                "Examples: \n\n"
                "cleanup_radios.exe -o --no-wds --no-snmp --no-ntp 10.8.85.0/26\n\n"
                "cleanup_radios.exe --no-ts 9-10.7-8.10-20.0-123\n\n"
                "cleanup_radios.exe -vv -m ping-only 10.7.76-79.0/24 10.7.176-179.0/24")

mode_help = ("-"*43 + "\nChange the mode of the script. default is to make configuration changes. ping-only & ssh-check-only are good for testing connectivity to radios. Even with the configuration flags set to True, the configuration will not run unless in 'configure' mode.")

wds_help = ("-"*43 + "\nEnable/Disable the script's WDS configuration. When flag is True, this will turn WDS on for all radios that are confiured, except airRouters. On an airRouter, the script will turn WDS off.")

snmp_help = ("-"*43 + "\nEnable/Disable the script's SNMP configuration. When flag is True, this will ensure that SNMP is enabled as well as set FWB for the location, contact, community fields if it is not set to FWB already.")

ntp_help = ("-"*43 + "\nEnable/Disable the script's NTP configuration. When flag is True, this will ensure that NTP is enabled as well as set the NTP server domain if it is not set already. If the NTP domain is set, this script will verify that it is correct.")

traffic_shaper_help = ("-"*43 + "\nEnable/Disable the script's traffic shaper removal. When flag is True, this will ensure that traffic shaping is disabled on all airMAX equipment confiured, both radios and airRouters.")

timezone_help = ("-"*43 + "\nEnable/Disable the script's timezone configuration. When flag is True, this will ensure that the timezone is set to US Eastern.")

ff_reporting_mode_help = ("-"*43 + "\nEnable/Disable the script's fixed frame capacity reporting mode configuration. When flag is True, this will ensure that the fixed frame capacity reporting mode is set to DL/UL split based. Rocket AC's should be the only types of equipment that have this setting. DL/UL split based show more accurate throughput values on the dashboard on the radio when fixed frame timing allocations are in use.")

show_options_help = ("-"*43 + "\nPrint out all of the options as they are set before the tool runs.")

verbose_help = ("-"*43 + "\nEnable verbose mode. Prints additional information as the tool runs.")

@click.command(help=command_help, context_settings=CONTEXT_SETTINGS, options_metavar='[options]')
@click.option('--mode', '-m', type=click.Choice( ('configure', 'ping-only', 'ssh-check-only'), case_sensitive=False), default='configure', show_default=True, help=mode_help)
@click.option('--wds/--no-wds', default=True, show_default=True, help=wds_help)
@click.option('--snmp/--no-snmp', default=True, show_default=True, help=snmp_help)
@click.option('--ntp/--no-ntp', default=True, show_default=True, help=ntp_help)
@click.option('--traffic-shaper-disable/--no-traffic-shaper-disable', '--ts/--no-ts', 'traffic_shaper', default=True, show_default=True, help=traffic_shaper_help)
@click.option('--timezone/--no-timezone', '--tz/--no-tz', 'timezone_', default=True, show_default=True, help=timezone_help)
@click.option('--ff-reporting-mode/--no-ff-reporting-mode', '--ffrm/--no-ffrm', default=True, show_default=True, help=ff_reporting_mode_help)
@click.option('--show-options', '-o', is_flag=True, help=show_options_help)
@click.option('-v', '--verbose', is_flag=True, help=verbose_help)
@click.argument('networks', nargs=-1, required=True, metavar='<*networks>')
def run_from_cli(networks, mode, wds, snmp, ntp, traffic_shaper, timezone_, ff_reporting_mode, show_options, verbose):

    options_nt = namedtuple('options', ('networks', 'mode', 'wds', 'snmp', 'ntp', 'traffic_shaper', 'timezone_', 
                                            'ff_reporting_mode', 'verbose') )

    cli_options = options_nt(networks, mode, wds, snmp, ntp, traffic_shaper, timezone_, 
                                ff_reporting_mode, verbose) 

    if show_options:
        click.echo(cli_options, '\n')

    device_cleanup(cli_options)

    

if __name__ == '__main__':
    run_from_cli()