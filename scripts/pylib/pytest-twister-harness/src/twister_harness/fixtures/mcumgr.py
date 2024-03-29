# Copyright (c) 2023 Nordic Semiconductor ASA
#
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
import logging
import re
import shlex

from typing import Generator
from subprocess import check_output, getstatusoutput
from pathlib import Path
from dataclasses import dataclass

from twister_harness.device.device_adapter import DeviceAdapter


logger = logging.getLogger(__name__)


class MCUmgrException(Exception):
    """General MCUmgr exception."""


@dataclass
class MCUmgrImage:
    image: int
    slot: int
    version: str = ''
    flags: str = ''
    hash: str = ''


class MCUmgr:
    """Sample wrapper for mcumgr command-line tool"""
    mcumgr_exec = 'mcumgr'

    def __init__(self, connection_options: str):
        self.conn_opts = connection_options

    @classmethod
    def create_for_serial(cls, serial_port: str) -> MCUmgr:
        return cls(connection_options=f'--conntype serial --connstring={serial_port}')

    @classmethod
    def is_available(cls) -> bool:
        exitcode, output = getstatusoutput(f'{cls.mcumgr_exec} version')
        if exitcode != 0:
            logger.warning(f'mcumgr tool not available: {output}')
            return False
        return True

    def run_command(self, cmd: str) -> str:
        command = f'{self.mcumgr_exec} {self.conn_opts} {cmd}'
        logger.info(f'CMD: {command}')
        return check_output(shlex.split(command), text=True)

    def reset_device(self):
        self.run_command('reset')

    def image_upload(self, image: Path | str, timeout: int = 30):
        self.run_command(f'-t {timeout} image upload {image}')
        logger.info('Image successfully uploaded')

    def get_image_list(self) -> list[MCUmgrImage]:
        output = self.run_command('image list')
        return self._parse_image_list(output)

    @staticmethod
    def _parse_image_list(cmd_output: str) -> list[MCUmgrImage]:
        image_list = []
        re_image = re.compile(r'image=(\d+)\s+slot=(\d+)')
        re_version = re.compile(r'version:\s+(\S+)')
        re_flags = re.compile(r'flags:\s+(.+)')
        re_hash = re.compile(r'hash:\s+(\w+)')
        for line in cmd_output.splitlines():
            if m := re_image.search(line):
                image_list.append(
                    MCUmgrImage(
                        image=int(m.group(1)),
                        slot=int(m.group(2))
                    )
                )
            elif image_list:
                if m := re_version.search(line):
                    image_list[-1].version = m.group(1)
                elif m := re_flags.search(line):
                    image_list[-1].flags = m.group(1)
                elif m := re_hash.search(line):
                    image_list[-1].hash = m.group(1)
        return image_list

    def get_hash_to_test(self) -> str:
        image_list = self.get_image_list()
        if len(image_list) < 2:
            logger.info(image_list)
            raise MCUmgrException('Please check image list returned by mcumgr')
        return image_list[1].hash

    def image_test(self, hash: str | None = None):
        if not hash:
            hash = self.get_hash_to_test()
        self.run_command(f'image test {hash}')

    def image_confirm(self, hash: str | None = None):
        if not hash:
            image_list = self.get_image_list()
            hash = image_list[0].hash
        self.run_command(f'image confirm {hash}')


@pytest.fixture(scope='session')
def is_mcumgr_available() -> None:
    if not MCUmgr.is_available():
        pytest.skip('mcumgr not available')


@pytest.fixture()
def mcumgr(is_mcumgr_available: None, dut: DeviceAdapter) -> Generator[MCUmgr, None, None]:
    yield MCUmgr.create_for_serial(dut.device_config.serial)
