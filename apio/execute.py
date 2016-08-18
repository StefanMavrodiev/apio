# Execute functions

import os
import re
import sys
import time
import click
import platform
import datetime

from os.path import join, dirname, isdir, isfile, expanduser
from .project import Project

from . import util
from .config import Boards


class System(object):
    def __init__(self):
        self.ext = ''
        if 'Windows' == platform.system():
            self.ext = '.exe'

    def lsusb(self):
        self._run('listdevs')

    def lsftdi(self):
        self._run('find_all')

    def detect_boards(self):
        detected_boards = []
        result = self._run('find_all')

        if result and result['returncode'] == 0:
            detected_boards = self.parse_out(result['out'])

        return detected_boards

    def _run(self, command):
        result = []
        system_dir = join(expanduser('~'), '.apio', 'system')
        tools_usb_ftdi_dir = join(system_dir, 'tools-usb-ftdi')

        if isdir(tools_usb_ftdi_dir):
            result = util.exec_command(
                os.path.join(tools_usb_ftdi_dir, command + self.ext),
                stdout=util.AsyncPipe(self._on_run_out),
                stderr=util.AsyncPipe(self._on_run_out)
                )
        else:
            click.secho('Error: system tools are not installed', fg='red')
            click.secho('Please run:\n'
                        '   apio install system', fg='yellow')

        return result

    def _on_run_out(self, line):
        click.secho(line)

    def parse_out(self, text):
        pattern = 'Number\sof\sFTDI\sdevices\sfound:\s(?P<n>\d+?)\n'
        match = re.search(pattern, text)
        n = int(match.group('n')) if match else 0

        pattern = '.*Checking\sdevice:\s(?P<index>.*?)\n.*'
        index = re.findall(pattern, text)

        pattern = '.*Manufacturer:\s(?P<n>.*?),.*'
        manufacturer = re.findall(pattern, text)

        pattern = '.*Description:\s(?P<n>.*?)\n.*'
        description = re.findall(pattern, text)

        detected_boards = []

        for i in range(n):
            board = {
                "index": index[i],
                "manufacturer": manufacturer[i],
                "description": description[i],
                "board": self.obtain_board(description[i])
            }
            detected_boards.append(board)

        return detected_boards

    def obtain_board(self, description):
        if 'Lattice FTUSB Interface Cable' in description:
            return 'icestick'
        if 'IceZUM Alhambra' in description:
            return 'icezum'
        if 'Dual RS232-HS' in description:
            return 'go-board'


class SCons(object):

    def clean(self):
        self.run('-c')

    def verify(self):
        self.run('verify')

    def sim(self):
        self.run('sim')

    def build(self, args):
        current_boards = Boards()

        # -- Check arguments
        var_board =  args['board']
        var_fpga = args['fpga']
        var_size = args['size']
        var_type = args['type']
        var_pack = args['pack']

        if var_board:
            if var_board in current_boards.boards:
                fpga = current_boards.boards[var_board]['fpga']
                if fpga in current_boards.fpgas:
                    fpga_size = current_boards.fpgas[fpga]['size']
                    fpga_type = current_boards.fpgas[fpga]['type']
                    fpga_pack = current_boards.fpgas[fpga]['pack']
                else:
                    pass
            else:
                # Unknown board
                click.secho(
                    'Error: unkown board: {0}'.format(var_board), fg='red')
                return 1
        else:
            if var_fpga:
                if var_fpga in current_boards.fpgas:
                    fpga_size = current_boards.fpgas[var_fpga]['size']
                    fpga_type = current_boards.fpgas[var_fpga]['type']
                    fpga_pack = current_boards.fpgas[var_fpga]['pack']
                else:
                    # Unknown fpga
                    click.secho(
                        'Error: unkown fpga: {0}'.format(var_fpga), fg='red')
                    return 1
            else:
                if var_size and var_type and var_pack:
                    fpga_size = var_size
                    fpga_type = var_type
                    fpga_pack = var_pack
                else:
                    # Insufficient arguments
                    missing = []
                    if not var_size:
                        missing += ['size']
                    if not var_type:
                        missing += ['type']
                    if not var_pack:
                        missing += ['pack']
                    pass
                    click.secho(
                        'Error: insufficient arguments: missing {0}'.format(
                            ', '.join(missing)), fg='red')
                    return 1

        # -- Build Scons variables list
        variables = self.format_vars({
            "fpga_size": fpga_size,
            "fpga_type": fpga_type,
            "fpga_pack": fpga_pack
        })

        self.run('build', variables, var_board)

    def upload(self, args):
        # TODO: + args
        self.run('upload')

    def time(self):
        # TODO: + args
        self.run('time')

    def run(self, command, variables=[], board=None):
        """Executes scons for building"""

        packages_dir = os.path.join(util.get_home_dir(), 'packages')
        icestorm_dir = os.path.join(packages_dir, 'toolchain-icestorm', 'bin')
        iverilog_dir = os.path.join(packages_dir, 'toolchain-iverilog', 'bin')
        scons_dir = os.path.join(packages_dir, 'tool-scons', 'script')
        sconstruct_name = 'SConstruct'

        # Give the priority to the packages installed by apio
        os.environ['PATH'] = os.pathsep.join(
            [iverilog_dir, icestorm_dir, os.environ['PATH']])

        # Add environment variables
        os.environ['IVL'] = os.path.join(
            packages_dir, 'toolchain-iverilog', 'lib', 'ivl')
        os.environ['VLIB'] = os.path.join(
            packages_dir, 'toolchain-iverilog', 'vlib', 'system.v')

        # -- Check for the icestorm tools
        if not isdir(icestorm_dir):
            click.secho('Error: icestorm toolchain is not installed', fg='red')
            click.secho('Please run:\n'
                        '   apio install icestorm', fg='yellow')

        # -- Check for the iverilog tools
        if not isdir(iverilog_dir):
            click.secho('Error: iverilog toolchain is not installed', fg='red')
            click.secho('Please run:\n'
                        '   apio install iverilog', fg='yellow')

        # -- Check for the scons
        if not isdir(scons_dir):
            click.secho('Error: scons toolchain is not installed', fg='red')
            click.secho('Please run:\n'
                        '   apio install scons', fg='yellow')

        # -- Check for the project configuration file
        """if (len(board_in_variables) == 0):
            # Get board from project
            p = Project()
            p.read()
            board = p.board
            board_flag = "board={}".format(p.board)
            variables.append(board_flag)"""

        # -- Check for the SConstruct file
        if not isfile(join(os.getcwd(), sconstruct_name)):
            click.secho('Using default SConstruct file', fg='yellow')
            variables += ['-f', join(dirname(__file__), sconstruct_name)]

        # -- Execute scons
        if isdir(scons_dir) and isdir(icestorm_dir):
            terminal_width, _ = click.get_terminal_size()
            start_time = time.time()

            if command == 'build' or \
               command == 'upload' or \
               command == 'time':
                if board:
                    processing_board = board
                else:
                    processing_board = 'custom board'
                click.echo("[%s] Processing %s" % (
                    datetime.datetime.now().strftime("%c"),
                    click.style(processing_board, fg="cyan", bold=True)))
                click.secho("-" * terminal_width, bold=True)

            click.secho("Executing: scons -Q {0} {1}".format(command, ' '.join(variables)))
            result = util.exec_command(
                [
                    os.path.normpath(sys.executable),
                    os.path.join(scons_dir, 'scons'),
                    '-Q',
                    command
                ] + variables,
                stdout=util.AsyncPipe(self._on_run_out),
                stderr=util.AsyncPipe(self._on_run_err)
            )

            # -- Print result
            exit_code = result['returncode']
            is_error = exit_code != 0
            summary_text = " Took %.2f seconds " % (time.time() - start_time)
            half_line = "=" * int(((terminal_width - len(summary_text) - 10) / 2))
            click.echo("%s [%s]%s%s" % (
                half_line,
                (click.style(" ERROR ", fg="red", bold=True)
                 if is_error else click.style("SUCCESS", fg="green",
                                              bold=True)),
                summary_text,
                half_line
            ), err=is_error)

            return exit_code

    def format_vars(self, args):
        """Format the given vars in the form: 'flag=value'"""
        variables = []
        for key, value in args.items():
            if value:
                variables += ["{0}={1}".format(key, value)]
        return variables

    def _on_run_out(self, line):
        fg = 'green' if 'is up to date' in line else None
        click.secho(line, fg=fg)

    def _on_run_err(self, line):
        time.sleep(0.01)  # Delay
        fg = 'red' if 'error' in line.lower() else 'yellow'
        click.secho(line, fg=fg)

    def create_sconstruct(self):
        sconstruct_name = 'SConstruct'
        sconstruct_path = join(os.getcwd(), sconstruct_name)
        local_sconstruct_path = join(dirname(__file__), sconstruct_name)

        if isfile(sconstruct_path):
            click.secho('Warning: ' + sconstruct_name + ' file already exists',
                        fg='yellow')
            if click.confirm('Do you want to replace it?'):
                self._copy_file(sconstruct_name, sconstruct_path,
                                local_sconstruct_path)
        else:
            self._copy_file(sconstruct_name, sconstruct_path,
                            local_sconstruct_path)

    def _copy_file(self, sconstruct_name,
                   sconstruct_path, local_sconstruct_path):
        click.secho('Creating ' + sconstruct_name + ' file ...')
        with open(sconstruct_path, 'w') as sconstruct:
            with open(local_sconstruct_path, 'r') as local_sconstruct:
                sconstruct.write(local_sconstruct.read())
                click.secho(
                    'File \'' + sconstruct_name +
                    '\' has been successfully created!',
                    fg='green')
