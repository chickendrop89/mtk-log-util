#!/usr/bin/env python3

# mtkclient wrapper for getting bootloader or kernel logs from a mediatek device
# Copyright (C) 2025 chickendrop89
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import argparse
import subprocess
import re
import logging
import tempfile
from pathlib import Path

# Global configuration variables
MTK_CLIENT_CMD = 'python mtkclient/mtk.py'

# Default values if no arguments are supplied.
MTK_CLIENT_ARGS = ''
# Extracted from MT6833P (opal).
PSTORE_ADDRESS = '0x48090000'
PSTORE_SIZE = '0xe0000'

def setup_logging() -> logging.Logger:
    """Configure logging"""

    class PrefixFormatter(logging.Formatter):
        def format(self, record):
            record.msg = f'[mtklogs] {record.msg}'
            return super().format(record)

    log = logging.getLogger('mtk-log-util')
    log.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(PrefixFormatter('%(message)s'))
    log.addHandler(handler)
    return log

def run_command(cmd: str) -> bool:
    """Execute a shell command and stream output."""

    logger.info('Executing command: %s', cmd)
    try:
        with subprocess.Popen(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=True, text=True,
            args=cmd, bufsize=1,
        ) as process:
            for line in iter(process.stdout.readline, ''):
                print(f'[mtkclient] {line.rstrip()}')

            return_code = process.wait()
            if return_code != 0:
                logger.error('Command failed with return code %s', return_code)
                return False

        return True
    except OSError as error:
        logger.error('Exception while running command: %s', error)
        return False

def extract_ascii_strings(output_file: Path, filename: Path, min_length: int = 4) -> None:
    """Extract ASCII strings from a binary."""

    try:
        with open(filename, 'rb') as fh:
            data = fh.read()

        # Regex to find printable ASCII strings
        ascii_strings = re.findall(rb'[\x20-\x7E]{' + str(min_length).encode() + rb',}', data)
        output_lines = [f'=== ASCII Strings from {filename} ===']

        for string in ascii_strings:
            try:
                decoded = string.decode('ascii')
                output_lines.append(decoded)
            except UnicodeDecodeError:
                continue

        with open(output_file, 'w', encoding='utf-8') as out_fh:
            out_fh.write('\n'.join(output_lines))

        logger.info('ASCII strings saved to %s', output_file)
    except OSError as error:
        logger.error('Error processing file %s: %s', filename, error)

def extract_with_mtkclient(extraction_type: str, output_filename: str,
    address: str = None, size: str = None, da: bool = True) -> bool:
    """Generic wrapper for mtkclient."""

    cmd : str

    if extraction_type == 'expdb':
        cmd =  f'{MTK_CLIENT_CMD} r expdb {output_filename} {MTK_CLIENT_ARGS}'
    elif extraction_type == 'pstore':
        cmd =  f'{MTK_CLIENT_CMD} {'da' if da else ''} peek {address} {size} '
        cmd += f'--filename {output_filename} {MTK_CLIENT_ARGS}'

    return run_command(cmd)

def detect_pstore_addr() -> tuple[str, str]:
    """Auto-detect pstore configuration from expdb partition."""

    def _find_pstore_config_in_data(data: bytes) -> tuple[str, str]:
        """Search for pstore configuration in binary data."""

        ascii_strings = re.findall(rb'[\x20-\x7E]{4,}', data)
        pstore_addr = pstore_size = None

        for string in ascii_strings:
            try:
                decoded = string.decode('ascii')

                # Look for individual patterns
                addr_match = re.search(r'pstore_addr[:\s]*0x([0-9a-fA-F]+)', decoded, re.IGNORECASE)
                if addr_match:
                    pstore_addr = f'0x{addr_match.group(1)}'
                    logger.info('Found pstore_addr: %s', pstore_addr)

                size_match = re.search(r'pstore_size[:\s]*0x([0-9a-fA-F]+)', decoded, re.IGNORECASE)
                if size_match:
                    pstore_size = f'0x{size_match.group(1)}'
                    logger.info('Found pstore_size: %s', pstore_size)

                if pstore_addr and pstore_size:
                    break
            except UnicodeDecodeError:
                continue

        return pstore_addr, pstore_size

    with tempfile.TemporaryDirectory() as tmp:
        raw_expdb_filename = f"{tmp}/expdb.bin"
        logger.info('Extracting expdb partition to detect pstore configuration...')

        if not extract_with_mtkclient('expdb', raw_expdb_filename):
            logger.error('Failed to extract expdb for pstore detection')
            return PSTORE_ADDRESS, PSTORE_SIZE

        try:
            with open(raw_expdb_filename, 'rb') as fh:
                data = fh.read()

            pstore_addr, pstore_size = _find_pstore_config_in_data(data)

            # Handle partial matches with fallbacks
            if pstore_addr and pstore_size:
                logger.info('Successfully detected pstore configuration from expdb')
                return pstore_addr, pstore_size
            if pstore_addr:
                logger.info('Found address but missing size, using default size')
                return pstore_addr, PSTORE_SIZE
            if pstore_size:
                logger.info('Found size but missing address, using default address')
                return PSTORE_ADDRESS, pstore_size

            logger.info('No pstore configuration found, using defaults')
            return PSTORE_ADDRESS, PSTORE_SIZE

        except OSError as error:
            logger.error('Error reading expdb file for pstore detection: %s', error)
            return PSTORE_ADDRESS, PSTORE_SIZE

def resolve_pstore_params(pstore_address: str, pstore_size: str,
    auto_detect: bool) -> tuple[str, str]:
    """Resolve pstore parameters."""

    if auto_detect:
        detected_addr, detected_size = detect_pstore_addr()
        address = pstore_address or detected_addr
        size = pstore_size or detected_size
    else:
        address = pstore_address or PSTORE_ADDRESS
        size = pstore_size or PSTORE_SIZE

    logger.info('Extracting pstore from memory (MemAddr: %s. Size: %s)', address, size)
    return address, size

def extract_expdb(output_file: Path) -> bool:
    """Extract and analyze expdb partition."""

    with tempfile.TemporaryDirectory() as tmp:
        raw_expdb_filename = f"{tmp}/expdb.bin"
        logger.info('Extracting expdb partition...')

        if extract_with_mtkclient('expdb', raw_expdb_filename):
            extract_ascii_strings(filename=raw_expdb_filename, output_file=output_file)
            return True

    logger.error('Failed to extract expdb partition')
    return False

def extract_pstore(output_file: Path, pstore_address: str = None,
    pstore_size: str = None, auto_detect: bool = False, da: bool = True) -> bool:
    """Extract and analyze pstore from memory."""

    address, size = resolve_pstore_params(pstore_address, pstore_size, auto_detect)

    with tempfile.TemporaryDirectory() as tmp:
        raw_pstore_filename = f"{tmp}/pstore.bin"

        if extract_with_mtkclient('pstore', raw_pstore_filename, address, size, da):
            extract_ascii_strings(filename=raw_pstore_filename, output_file=output_file)
            return True

    logger.error('Failed to extract pstore from memory')
    return False

def main() -> bool:
    """Main entry point"""

    parser = argparse.ArgumentParser(
        description='''mtk-log-util - mtkclient wrapper for getting bootloader
        or kernel logs from a mediatek device'''
    )
    parser.add_argument(
        'command', 
        choices=['expdb', 'pstore'],
        help='Choose extraction method: expdb (partition) or pstore (memory)'
    )
    parser.add_argument(
        'filename',
        type=str,
        help='Output file to save ASCII strings'
    )
    parser.add_argument(
        '--mtkclient-args', 
        type=str,
        help=f'Extra mtkclient arguments (default: "{MTK_CLIENT_ARGS}")'
    )
    parser.add_argument(
        '--pstore-address',
        type=str,
        help=f'Pstore memory address (default: {PSTORE_ADDRESS})'
    )
    parser.add_argument(
        '--pstore-size', 
        type=str,
        help=f'Pstore memory size (default: {PSTORE_SIZE})'
    )
    parser.add_argument(
        '--auto-detect-pstore',
        action='store_true',
        help='Auto-detect pstore address and size from expdb partition (pstore only)'
    )
    parser.add_argument(
        '--dont-peek-via-da',
        action='store_false',
        help='Don\'t do a peek via Download Agent (use in case of issues) (pstore only)'
    )
    args = parser.parse_args()

    if args.auto_detect_pstore or args.dont_peek_via_da and args.command != 'pstore':
        logger.warning('This argument is valid only with pstore command, ignoring')

    logger.info('Output file: %s', args.filename)
    output_file = Path(args.filename)

    if args.command == 'expdb':
        return extract_expdb(output_file)
    if args.command == 'pstore':
        return extract_pstore(
            output_file, args.pstore_address,
            args.pstore_size, args.auto_detect_pstore,
            args.dont_peek_via_da
        )

    return False

logger = setup_logging()

if __name__ == '__main__':
    main()
