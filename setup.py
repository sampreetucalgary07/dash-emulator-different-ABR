#!/usr/bin/env python3

from setuptools import find_packages, setup

requirements = [
    "wsproto",
    "uvloop",
    "aiohttp",
    "requests",
    "matplotlib",
    "behave",
    "aioquic",
    "scipy",
    "pyyaml",
    "dash-emulator @ git+https://github.com/sampreetucalgary07/dash-emulator#egg=dash-emulator",
]
# https://github.com/navidakbari/dash-emulator#egg=dash-emulator
setup(
    name="dash-emulator-quic",
    version="0.2.0.dev0",
    description="A headless player to emulate the playback of MPEG-DASH streams over QUIC",
    author="Yang Liu",
    author_email="yang.jace.liu@linux.com",
    url="https://github.com/navidakbari/dash-emulator-different-ABR/",
    packages=find_packages(),
    scripts=["scripts/dash-emulator.py", "scripts/dash-emulator-analyze.py"],
    install_requires=requirements,
    include_package_data=True,
    package_data={"": ["resources/*"]},
)
