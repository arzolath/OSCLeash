# OSCLeash

Move a VRChat avatar in the direction of a stretched PhysBone. Useful for leashes, tails, and hand holding.

Maintained by [Arzolath](https://github.com/arzolath), based on [ZenithVal's original OSCLeash](https://github.com/ZenithVal/OSCLeash). This fork adds OSC connection diagnostics, configurable verbose logging, and fixes to movement handling and OSCQuery startup.

[![Version](https://img.shields.io/github/v/tag/arzolath/OSCLeash?label=Version&sort=semver)](https://github.com/arzolath/OSCLeash/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Download and setup

Release builds, when available, are listed on the [releases page](https://github.com/arzolath/OSCLeash/releases). To use the current source code, follow [Running from source](#running-from-source).

The release workflow produces these packages:

| Platform | File | Format |
| --- | --- | --- |
| Windows | `OSCLeash-Installer.msi` | Installer |
| Windows | `OSCLeash.exe` | Standalone executable built with Nuitka |
| Windows | `OSCLeash-Py.exe` | Standalone executable built with PyInstaller |
| Linux | `OSCLeash-Linux.AppImage` | AppImage launched from a terminal |

### Unity setup

A leash model is not included. Use an existing leash, tail, or other suitable PhysBone chain on the avatar.

1. Add [OSCLeash.prefab](Unity/OSCLeash.prefab) to the Unity project.
2. Place the prefab at the avatar root, outside the armature. Keep the prefab intact.
3. Select `Leash Physbone` and assign its Root Transform to the first bone of the leash.
4. Select `Compass` and assign the source of its Position Constraint to the **first** bone of the leash.
5. Select `Aim Needle`, a child of `Compass`, and assign the source of its Aim Constraint to the **last** bone of the leash.
6. Optionally, use `IsLocal` to disable the compass for remote users.
7. For PC/Quest avatar compatibility, synchronize the PhysBone network IDs. See [FAQ](#faq).
8. Enable OSC in VRChat. If the avatar's parameters have changed, reset its OSC configuration.
9. Start OSCLeash, then grab and stretch the leash to test movement.
10. Adjust the [configuration](#config) to tune movement.

For connection problems, start with [Troubleshooting OSC reception](#troubleshooting-osc-reception). Report unresolved problems through this fork's [issue tracker](https://github.com/arzolath/OSCLeash/issues).

## Config

OSCLeash generates a `Config.json` file on its first run.
  
This configuration file will be located at `%LocalAppData%\Programs\OSCLeash\Config.json` (Windows), `$XDG_CONFIG_HOME/OSCLeash/Config.json` (Linux), or `$HOME/.config/OSCLeash/Config.json` (Linux, fallback). The `OSCLEASH_CONFIG_PATH` environment variable can be used to override the default config location. 
   
Edit `Config.json` with a text editor, then restart OSCLeash to apply changes.

<details><summary>Configuration settings</summary>

---

| Value                 | Info                                                           | Default     |
|:--------------------- | -------------------------------------------------------------- |:-----------:|
| IP                    | VRChat address to send OSC data to                             | 127.0.0.1   |
| BindIP                | Local interface to receive OSC on; use 0.0.0.0 for LAN receivers | 127.0.0.1 |
| ListeningPort         | Receive port; ignored when UseOSCQuery is true                                 | 9001        |
| SendingPort           | Port to send OSC data to                                       | 9000        |
| RunDeadzone           | Minimum Stretch % to cause running                             | 0.70        |
| WalkDeadzone          | Minimum Stretch % to start walking                             | 0.15        |
| StrengthMultiplier    | Multiplies speed values but they can't go above (1.0)          | 1.2         |
| UpDownCompensation    | % of compensation to apply for Up/Down angles                  | 1.0         |
| UpDownDeadzone        | Stops movement if pull angle is above/below this. 1.0 Disables | 0.5         |
| TurningEnabled        | Enable turning functionality                                   | false       |
| TurningMultiplier     | Adjust turning speed                                           | 0.80        |
| TurningDeadzone       | Minimum Stretch % to start turning                             | 0.15        |
| TurningGoal           | Goal degree range for turning. (degrees, 0-144) (0° to 144°)   | 90          |
| ActiveDelay           | Delay in seconds between OSC messages while active             | 0.02        |
| InactiveDelay         | Delay in seconds for OSCLeash while not in use                 | 0.5         |
| Logging               | Print directional compass values while grabbed                | false       |
| VerboseLogging        | Timestamped OSC receive/send messages, unmapped addresses and connection diagnostics | false |
| XboxJoystickMovement  | Optional movement through an emulated Xbox controller        | false       |
| UseOSCQuery           | Enables [OSCQuery](https://docs.vrchat.com/docs/oscquery)      | false       |
| PhysboneParameters    | A list of Physbones that are leashes                           | see below   |
| DirectionalParameters | A list of contacts to use for direction calculation            | see below   |
---
</details><br>

<details><summary>Default Config.json</summary>

---
```json
{
        "IP": "127.0.0.1",
        "BindIP": "127.0.0.1",
        "ListeningPort": 9001,
        "SendingPort": 9000,
        "RunDeadzone": 0.70,
        "WalkDeadzone": 0.15,
        "StrengthMultiplier": 1.2,
        "UpDownCompensation": 1.0,
        "UpDownDeadzone": 0.5,
        "TurningEnabled": false,
        "TurningMultiplier": 0.80,
        "TurningDeadzone": 0.15,
        "TurningGoal": 90,
        "ActiveDelay": 0.02,
        "InactiveDelay": 0.5,
        "Logging": false,
        "VerboseLogging": false,
        "XboxJoystickMovement": false,
        "UseOSCQuery": false,
        
        "PhysboneParameters":
        [
                "Leash"
        ],
        "DirectionalParameters":
        {
                "Z_Positive_Param": "Leash_Z+",
                "Z_Negative_Param": "Leash_Z-",
                "X_Positive_Param": "Leash_X+",
                "X_Negative_Param": "Leash_X-",
                "Y_Positive_Param": "Leash_Y+",
                "Y_Negative_Param": "Leash_Y-"
        }
}
```
---
</details><br>

<details><summary>Physbone Parameters</summary>

---
List the PhysBone parameter names used for leashes.

```json
        "PhysboneParameters":
        [
            "Leash",
            "Leash2",
            "Leash3"
        ],
```

OSCLeash listens for the `_IsGrabbed` and `_Stretch` parameters for every listed leash.

---
</details><br>

<details><summary>Multiple Leashes</summary>

---
This requires an understanding of Physbones Parameters, Animations, and Constraints. <br/>
 - Add a new source to `Compass` and `Aim Needle` for each extra leash. 0 Weight by default
 - Depending on which leash `_IsGrabbed`, animate the weights to match the Grabbed leash.

 ---
</details><br>

<details><summary>Turning functionality</summary>

Turning is optional and may cause motion sickness. Set `"TurningEnabled": true` to enable it.

The PhysBone parameter name must end in `_North`, `_South`, `_East`, or `_West` to identify the leash's attachment direction. For example, use `Leash_North` for a leash attached at the front of the avatar, or `Tail_South` for a tail at the back. The name in the avatar and `PhysboneParameters` must match.

```json
"PhysboneParameters": ["Leash_North"]
```

`TurningDeadzone` sets the stretch threshold for turning, `TurningMultiplier` controls its strength, and `TurningGoal` sets the target angle. Turning also stops below the walking deadzone. Leashes without a recognized direction suffix continue to support movement, but do not turn the avatar.

</details>

## How OSCLeash works

OSCLeash receives the avatar's `_IsGrabbed` and `_Stretch` parameters, along with six directional contact values. While a leash is grabbed, the compass contacts determine the direction of movement.

Before compensation and output limits, the movement calculation is:

```text
Vertical   = (Z_Positive - Z_Negative) * Stretch * StrengthMultiplier
Horizontal = (X_Positive - X_Negative) * Stretch * StrengthMultiplier
```

The Y contacts control vertical-angle compensation and the up/down cutoff. Final movement values are limited to the range -1 to 1.

Stretch above `WalkDeadzone` enables movement. Stretch above `RunDeadzone` also sends the run input; the world's movement settings determine the resulting speed. Releasing the leash sends neutral inputs twice to reduce the chance of a lost UDP packet leaving movement active. Avatar changes reset the stored leash state.

## Troubleshooting OSC reception

Set `"VerboseLogging": true` in the config path printed at startup, then restart OSCLeash. On Windows this is normally `%LocalAppData%\Programs\OSCLeash\Config.json`, even when running from source. To use the repository's config instead, set `$env:OSCLEASH_CONFIG_PATH = "$PWD/Config.json"` in PowerShell before launching it. Existing configs can omit the new settings; their defaults are filled in without rewriting the file.

Verbose output includes the actual listening address and port, incoming `OSC RX` messages with source addresses, `Unmapped OSC address` messages, outgoing `OSC TX` messages and a summary every ten seconds. `Logging` remains the separate compass-value display. The console is no longer cleared during movement.

1. **No `OSC RX` lines:** Enable OSC in VRChat's Action Menu. With `UseOSCQuery` disabled, VRChat normally sends to UDP 9001 and receives on UDP 9000. Match OSCLeash's `ListeningPort` and `SendingPort` to any custom VRChat `--osc=inPort:senderIP:outPort` launch option. `IP` is the destination running VRChat; `BindIP` must refer to this computer. See [VRChat's port documentation](https://docs.vrchat.com/docs/osc-overview).
2. **A bind error at startup:** Another receiver may already own the UDP port. On Windows, `Get-NetUDPEndpoint -LocalPort 9001 | Select-Object LocalAddress,LocalPort,OwningProcess` identifies the listener. Close duplicate instances or set `"UseOSCQuery": true` to use a separately allocated receive port. The program reports startup failures directly.
3. **Using OSCQuery:** Keep `BindIP` at `127.0.0.1`. OSCLeash prints its allocated UDP and TCP ports; `ListeningPort` is ignored. Look for VRChat's notification that it is sending data to `OSCLeash-...`. If discovery fails, toggle OSC off/on in VRChat after starting OSCLeash. Allow the application through the firewall: discovery uses mDNS (UDP 5353), an allocated TCP query port and an allocated UDP receive port, so allowing only 9000/9001 does not cover this mode. `IP` and `SendingPort` still select where movement commands go. See [VRChat's OSCQuery guide](https://github.com/vrchat-community/osc/wiki/OSCQuery).
4. **OSC arrives, but leash parameters do not match:** Compare the received addresses to the names in `PhysboneParameters` and `DirectionalParameters`, including capitalization. The default prefab uses `Leash_IsGrabbed`, `Leash_Stretch`, and `Leash_Z+`, `Leash_Z-`, `Leash_X+`, `Leash_X-`, `Leash_Y+`, `Leash_Y-`, all below `/avatar/parameters/`. After changing the avatar, use VRChat's OSC Reset Config command and reload the avatar if needed. Its generated [avatar OSC config](https://docs.vrchat.com/docs/osc-avatar-parameters) controls outgoing parameter addresses.
5. **Grab messages arrive, but movement stays zero:** Check stretch and directional values in the log. Enable avatar self interaction for the compass contacts, and check PhysBone stretch. VRChat sends parameter changes; a missing-parameter warning alone does not prove the avatar is broken. Grab, stretch and move the leash through several directions while logging.
6. **Nonzero `OSC TX` values, but no movement:** Check `IP` and `SendingPort`, and open [VRChat's OSC Debug view](https://docs.vrchat.com/docs/osc-debugging) to inspect incoming commands. A successful UDP send does not confirm that VRChat received it.

For a LAN setup, disable `UseOSCQuery`, set `IP` to the VRChat computer's address, and set `BindIP` to the OSCLeash computer's local address or `0.0.0.0`. Configure VRChat's output destination to point to the OSCLeash computer. Older versions incorrectly used `IP` for both sending and binding.

You can test reception without VRChat by running `python Testing/OSC_SimpleTestSender.py --port 9001` in a second terminal. With OSCQuery enabled, substitute the allocated UDP port printed by OSCLeash. The sender uses the default compass names and grabs `Leash` for five seconds before releasing it; `--leash` selects a different PhysBone name. It generates real movement commands if VRChat is running.

Use Ctrl+C for a clean shutdown that sends neutral movement inputs and closes the receiver. A forced process kill or lost UDP release packet cannot guarantee a stop. There is no inactivity timeout because unchanged avatar parameters are not a heartbeat.

## FAQ

<details><summary>An antivirus flags or removes the executable</summary>

Packaged Python executables can trigger antivirus detections. Check that the download came from this fork's releases and review the detection before deciding how to proceed. Running from source is another option.

</details>

<details><summary>OSCLeash stays at "Started, awaiting input"</summary>

See [Troubleshooting OSC reception](#troubleshooting-osc-reception). The console distinguishes missing traffic from unmatched avatar parameters.

</details>

<details><summary>The prefab has missing scripts</summary>

Check that the VRChat SDK is installed and up to date, and resolve any Unity compilation errors. A third-party prefab that uses [Modular Avatar](https://modular-avatar.nadena.dev/) also requires that package.

</details>

<details><summary>The leash is grabbed, but the avatar does not move</summary>

Check that the PhysBone allows stretching and that avatar self interaction is enabled for the directional contacts. Enable `VerboseLogging` to inspect the received stretch values, compass values, and outgoing movement commands.

</details>

<details><summary>The pull direction is inaccurate</summary>

Check the PhysBone's angle limits and length. A chain that cannot move far enough may not produce a useful direction. At large avatar scales, the compass may also need to be scaled down to stay within contact size limits.

</details>

<details><summary>PC and Quest compatibility</summary>

OSCLeash runs on a computer. For interactions between PC and Quest versions of an avatar, synchronize the leash PhysBone's network IDs between both versions. Tools include [VRChat's Network ID Utility](https://creators.vrchat.com/worlds/udon/networking/network-id-utility/) and the [VRCQuestTools ID Assigner](https://kurotu.github.io/VRCQuestTools/docs/references/components/network-id-assigner/).

Receiving OSC from a separate device requires a LAN setup; see the connection troubleshooting section.

</details>

<details><summary>Using OSCLeash alongside other OSC applications</summary>

Set `"UseOSCQuery": true` for discovery on the same computer. Each receiving application can then use its own UDP port. For fixed-port setups, an OSC router can forward messages to multiple applications.

</details>

For other problems, open an [issue](https://github.com/arzolath/OSCLeash/issues) with the operating system, OSCLeash version, relevant configuration, and verbose log output from a grab/stretch/release attempt.

## Running from source

Requires Python 3.10 or newer. From the repository directory:

```sh
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python OSCLeash.py
```

The virtual Xbox controller is optional. Only install `requirements-gamepad.txt` if you use `XboxJoystickMovement`; OSC movement does not need a gamepad driver.

Run the regression tests with:

```sh
python -m unittest discover -s Testing -p "test_*.py" -v
```

The tests exercise real local UDP traffic and the OSCQuery HTTP tree. They do not need a running VRChat client or gamepad driver.

## Credits and license

- [Arzolath](https://github.com/arzolath) — maintainer of this fork; OSC connectivity fixes, movement handling updates, and verbose logging.
- [ZenithVal](https://github.com/ZenithVal) — original creator of [OSCLeash](https://github.com/ZenithVal/OSCLeash).
- [ALeonic](https://github.com/ALeonic) — contributor responsible for much of the original v2 implementation.
- [FrostbyteVR](https://github.com/FrostbyteVR) — helped with development of the original v1 implementation.
- [Game-icons.net](https://game-icons.net/1x1/delapouite/locked-heart.html) — application icon, licensed under [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/).

OSCLeash is distributed under the [MIT License](LICENSE). The original copyright notice is retained.
