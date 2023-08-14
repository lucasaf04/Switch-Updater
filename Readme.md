# Switch Updater

[![License: GPL v3](https://img.shields.io/badge/License-GPL%20v3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Script to update your custom firmware setup.

Packing into a zip file for [AIO Switch Updater](https://github.com/HamletDuFromage/aio-switch-updater) is also supported.

## Initial setup

### Create a Python virtual environment

```sh
python3 -m venv .venv
```

### Activate the environment

```sh
source ./.venv/bin/activate
```

### Install dependencies

```sh
pip3 install -r requirements.txt
```

### Create a GitHub Token

Use this [link](https://github.com/settings/tokens/new?description=switch-updater%20(no%20scope%20required)), then paste it into `./github.token`. It is used to increase the GitHub API rate limit.

## Example configuration

Check [downloads.toml](./downloads.toml) and [config files](./config_files/).

## Usage

```txt
usage: python3 main.py [-h] [--debug] [--mariko] [--no-config] [--rebuild] [--pack PACK]

options:
  -h, --help   show this help message and exit
  --debug      Enable debug mode
  --mariko     Enable mariko mode
  --no-config  Disable copying config files
  --rebuild    Delete previously downloaded files
  --pack PACK  Name of the zip file to create
```

## Todo

- [ ] Erista mode (default behavior)
- [ ] Add `tegraexplorer_scripts` section
