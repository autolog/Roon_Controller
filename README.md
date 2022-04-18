# Roon Controller

Plugin for the Indigo Home Automation system.

The Roon Controller plugin enables you to control a Roon music player directly from Indigo.


| Requirement            |                     |   |
|------------------------|---------------------|---|
| Minimum Indigo Version | 2022.1              |   |
| Python Library (API)   | Third Party | Pyroon [see note below]  |
| Requires Local Network | Yes                 |   |
| Requires Internet      | No            	   |   |
| Hardware Interface     | None                |   |

## Quick Start

1. Install Plugin
2. Authorise plugin extension in Roon
3. Configure plugin for auto discovery
4. Let plugin discover and create Roon outputs and zones

The plugin uses a lightly modified version of the [Roon Python Library][2] created by Marcel van der Veldt and now also maintained by Greg Dowling et al.

[1]: https://www.indigodomo.com
[2]: https://github.com/pavoni/pyroon

**PluginID**: com.autologplugin.indigoplugin.rooncontroller