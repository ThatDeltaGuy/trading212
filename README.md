# Trading212 Custom Integration

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]

[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

A custom component for Trading212

## Installation

1. Use [HACS](https://hacs.xyz/docs/setup/download), in `HACS > Integrations > Explore & Add Repositories` search for "Trading212".
2. Restart Home Assistant.
3. [![Add Integration][add-integration-badge]][add-integration] or in the HA UI go to "Settings" -> "Devices & Services" then click "+" and search for "Trading212".


<!---->

## Usage

The `Trading212` integration offers integration with the Trading212 API. This provides a device per position, each device will have 6 entities as shown below.

This integration provides the following entities:
.
- Sensors - current price, average price, quantity, current value, buy value, percent change.

## Options

- Seconds between polling - Number of seconds between each call for data from the Trading212 API, default is 5 seconds.

---

[commits-shield]: https://img.shields.io/github/commit-activity/w/ThatDeltaGuy/trading212?style=for-the-badge
[commits]: https://github.com/ThatDeltaGuy/trading212/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license]: LICENSE
[license-shield]: https://img.shields.io/github/license/ThatDeltaGuy/trading212.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40ThatDeltaGuy-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/ThatDeltaGuy/trading212.svg?style=for-the-badge
[releases]: https://github.com/ThatDeltaGuy/trading212/releases
[user_profile]: https://github.com/ThatDeltaGuy
[add-integration]: https://my.home-assistant.io/redirect/config_flow_start?domain=trading212
[add-integration-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
