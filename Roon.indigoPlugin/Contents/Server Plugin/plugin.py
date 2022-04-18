#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Roon Controller © Autolog 2019-2022
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import copy
import logging
import os
import platform
from PIL import Image
try:
    import requests  # noqa
except ImportError:
    pass
from shutil import copyfile
import socket
import sys
import traceback

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
from roon import RoonApi


# noinspection PyUnresolvedReferences
class Plugin(indigo.PluginBase):

    # =============================================================================
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):

        indigo.PluginBase.__init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals[PLUGIN_INFO] = dict()
        self.globals[PLUGIN_INFO][PLUGIN_ID] = plugin_id
        self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME] = plugin_display_name
        self.globals[PLUGIN_INFO][PLUGIN_VERSION] = plugin_version
        self.globals[PLUGIN_INFO][PATH] = indigo.server.getInstallFolderPath()
        self.globals[PLUGIN_INFO][API_VERSION] = indigo.server.apiVersion
        self.globals[PLUGIN_INFO][INDIGO_SERVER_ADDRESS] = indigo.server.address

        # Initialise dictionary for debug log levels in plugin Globals
        # self.globals[DEBUG] = dict()

        # Setup Logging - Logging info:
        #   self.indigo_log_handler - writes log messages to Indigo Event Log
        #   self.plugin_file_handler - writes log messages to the plugin log

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s",
                                       datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(LOG_LEVEL_INFO)   # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.ROON")

        # Now logging is set-up, output Initialising message

        startup_message_ui = "\n"  # Start with a line break
        startup_message_ui += f"{' Initialising Roon Controller Plugin ':={'^'}130}\n"

        startup_message_ui += f"{'Plugin Name:':<31} {self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME]}\n"
        startup_message_ui += f"{'Plugin Version:':<31} {self.globals[PLUGIN_INFO][PLUGIN_VERSION]}\n"
        startup_message_ui += f"{'Plugin ID:':<31} {self.globals[PLUGIN_INFO][PLUGIN_ID]}\n"
        startup_message_ui += f"{'Indigo Version:':<31} {indigo.server.version}\n"
        startup_message_ui += f"{'Indigo License:':<31} {indigo.server.licenseStatus}\n"
        startup_message_ui += f"{'Indigo API Version:':<31} {indigo.server.apiVersion}\n"
        machine = platform.machine()
        startup_message_ui += f"{'Architecture:':<31} {machine}\n"
        sys_version = sys.version.replace("\n", "")
        startup_message_ui += f"{'Python Version:':<31} {sys_version}\n"
        startup_message_ui += f"{'Mac OS Version:':<31} {platform.mac_ver()[0]}\n"
        startup_message_ui += f"{'Install Path:':<31} {self.globals[PLUGIN_INFO][PATH]}\n"
        startup_message_ui += f"{'':={'^'}130}\n"
        self.logger.info(startup_message_ui)

        # Initialise dictionary to store configuration info
        self.globals[CONFIG] = dict()
        self.globals[CONFIG][PRINT_OUTPUTS_SUMMARY] = True  
        self.globals[CONFIG][PRINT_OUTPUT] = True
        self.globals[CONFIG][PRINT_ZONES_SUMMARY] = True  
        self.globals[CONFIG][PRINT_ZONE] = True
        self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME] = ""
        self.globals[CONFIG][ROON_DEVICE_FOLDER_ID] = 0 
        self.globals[CONFIG][ROON_CORE_IP_ADDRESS] = ""
        self.globals[CONFIG][DISPLAY_TRACK_PLAYING] = False
               
        # Initialise dictionary to store internal details about Roon
        self.globals[ROON] = dict()
        self.globals[ROON][INDIGO_DEVICE_BEING_DELETED] = dict()
        self.globals[ROON][ZONES] = dict()
        self.globals[ROON][OUTPUTS] = dict()

        self.globals[ROON][MAP_ZONE] = dict()  
        self.globals[ROON][MAP_OUTPUT] = dict()  # TODO: Not sure this is being used in a meaningful way?
        self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID] = dict()
        self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID] = dict()
        self.globals[ROON][OUTPUT_ID_TO_DEV_ID] = dict()

        self.globals[ROON][PLUGIN_PREFS_FOLDER] = f"{self.globals[PLUGIN_INFO][PATH]}/Preferences/Plugins/com.autologplugin.indigoplugin.rooncontroller"
        if not os.path.exists(self.globals[ROON][PLUGIN_PREFS_FOLDER]):
            self.mkdir_with_mode(self.globals[ROON][PLUGIN_PREFS_FOLDER])

        self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS] = OUTPUT_MAP_NUMBERS
        self.globals[ROON][AVAILABLE_ZONE_ALPHAS] = ZONE_MAP_ALPHAS

        # Initialise info to register with the Roon API
        self.globals[ROON][EXTENSION_INFO] = dict()
        self.globals[ROON][EXTENSION_INFO]['extension_id'] = "indigo_plugin_roon"
        self.globals[ROON][EXTENSION_INFO]['display_name'] = "Indigo Plugin for Roon"
        self.globals[ROON][EXTENSION_INFO]['display_version'] = "1.0.0"
        self.globals[ROON][EXTENSION_INFO]['publisher'] = "autolog"
        self.globals[ROON][EXTENSION_INFO]['email'] = "my@email.com"

        # Set Plugin Config Values
        self.getPrefsConfigUiValues()
        self.closedPrefsConfigUi(plugin_prefs, False)

        self.globals[DEVICES_TO_ROON_CONTROLLER_TABLE] = dict()  # TODO: Is this used?

    def __del__(self):

        indigo.PluginBase.__del__(self)

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = log_message + f"\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = log_message + f" at line {line_number}"
        self.logger.error(log_message)

    def closedDeviceConfigUi(self, values_dict, userCancelled, type_id, dev_id):  # noqa [Parameters not used]
        try:
            self.logger.debug(f"'closedDeviceConfigUi' called with userCancelled = {userCancelled}")

            if userCancelled:
                return

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    # def createOutputDevice(self, zone_id):
    #     pass

    # def createZoneDevice(self, zone_id):
    #     pass

    def closedPrefsConfigUi(self, values_dict, userCancelled):
        try:
            self.logger.debug(f"'closePrefsConfigUi' called with userCancelled = {userCancelled}")

            if userCancelled:
                return

            # Get required Event Log and Plugin Log logging levels
            plugin_log_level = int(values_dict.get("pluginLogLevel", LOG_LEVEL_INFO))
            event_log_level = int(values_dict.get("eventLogLevel", LOG_LEVEL_INFO))

            # Ensure following logging level messages are output
            self.indigo_log_handler.setLevel(LOG_LEVEL_INFO)
            self.plugin_file_handler.setLevel(LOG_LEVEL_INFO)

            # Output required logging levels and TP Message Monitoring requirement to logs
            self.logger.info(f"Logging to Indigo Event Log at the '{LOG_LEVEL_TRANSLATION[event_log_level]}' level")
            self.logger.info(f"Logging to Plugin Event Log at the '{LOG_LEVEL_TRANSLATION[plugin_log_level]}' level")

            # Now set required logging levels
            self.indigo_log_handler.setLevel(event_log_level)
            self.plugin_file_handler.setLevel(plugin_log_level)

            # ### IP Address ###

            self.globals[CONFIG][ROON_CORE_IP_ADDRESS] = values_dict.get('roonCoreIpAddress', "")
            try:
                self.globals[CONFIG][ROON_CORE_PORT] = int(values_dict.get('roonCorePort', 9300))
            except ValueError:
                self.globals[CONFIG][ROON_CORE_PORT] = 9300

            # ### AUTO-CREATE DEVICES + DEVICE FOLDER ###
            self.globals[CONFIG][AUTO_CREATE_DEVICES] = values_dict.get("autoCreateDevices", False)
            self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME] = values_dict.get("roonDeviceFolderName", "Roon")
            self.globals[CONFIG][DYNAMIC_GROUPED_ZONES_RENAME] = values_dict.get("dynamicGroupedZonesRename", True)

            # Create Roon Device folder name (if specific device folder required)
            if self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME] == '':
                self.globals[CONFIG][ROON_DEVICE_FOLDER_ID] = 0  # No specific device folder required
            else:
                if self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME] not in indigo.devices.folders:
                    indigo.devices.folder.create(self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME])
                self.globals[CONFIG][ROON_DEVICE_FOLDER_ID] = indigo.devices.folders.getId(
                    self.globals[CONFIG][ROON_DEVICE_FOLDER_NAME])

            # Create Roon Variable folder name (if required)
            self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME] = values_dict.get("roonVariableFolderName", '')

            self.globals[CONFIG][ROON_VARIABLE_FOLDER_ID] = 0  # Not required

            if self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME] != '':

                if self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME] not in indigo.variables.folders:
                    indigo.variables.folder.create(self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME])

                self.globals[CONFIG][ROON_VARIABLE_FOLDER_ID] = indigo.variables.folders[
                    self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME]].id

            self.logger.debug(f"Roon Variable Folder Id: {self.globals[CONFIG][ROON_VARIABLE_FOLDER_ID]}, Roon Variable Folder Name: {self.globals[CONFIG][ROON_VARIABLE_FOLDER_NAME]}")

            # Display Track playing info in Indigo UI Notes field: True / False
            self.globals[CONFIG][DISPLAY_TRACK_PLAYING] = values_dict.get("displayTrackPlayingInIndigoUi", False)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceDeleted(self, dev):
        try:
            self.globals[ROON][INDIGO_DEVICE_BEING_DELETED][dev.id] = dev.address

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            super(Plugin, self).deviceDeleted(dev)

    def deviceStartComm(self, dev):
        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                zone_dev_plugin_props = zone_dev.pluginProps
                zone_unique_identity_key = zone_dev_plugin_props.get('roonZoneUniqueIdentityKey', '')
                if zone_unique_identity_key != '':
                    self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key] = zone_dev.id

                zone_id = ""
                for found_zone_id in self.globals[ROON][ZONES]:
                    if ZONE_UNIQUE_IDENTITY_KEY in self.globals[ROON][ZONES][found_zone_id]:
                        if zone_unique_identity_key == self.globals[ROON][ZONES][found_zone_id][ZONE_UNIQUE_IDENTITY_KEY]:
                            zone_id = found_zone_id

                            # LOGIC TO HANDLE PLUGIN PROPS 'roonZoneId' ?????
                            dev_plugin_props = dev.pluginProps
                            dev_plugin_props['roonZoneId'] = zone_id
                            dev.replacePluginPropsOnServer(dev_plugin_props)

                            break

                try:
                    shared_props = dev.sharedProps
                    shared_props["sqlLoggerIgnoreStates"] = "queue_time_remaining, remaining, seek_position, ui_queue_time_remaining, ui_remaining, ui_seek_position"
                    dev.replaceSharedPropsOnServer(shared_props)
                except:  # noqa
                    pass

                if zone_dev.address[0:5] != 'ZONE-':
                    # At this point it is a brand new Roon Zone device as address not setup

                    if zone_id != '':
                        output_count = self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]
                    else:
                        output_count = 0
                    address_alpha = self.globals[ROON][AVAILABLE_ZONE_ALPHAS].pop(0)
                    if address_alpha[0:1] == '_':
                        address_alpha = address_alpha[1:2]
                    if output_count > 0:
                        address = f"ZONE-{address_alpha}-{output_count}"
                    else:
                        address = f"ZONE-{address_alpha}"
                    zone_dev_plugin_props["address"] = address
                    zone_dev.replacePluginPropsOnServer(zone_dev_plugin_props)

                # At this point it is an existing Roon Zone device as address already setup

                if zone_id == '':
                    # Flag as disconnected as Zone doesn't exist
                    self.disconnect_roon_zone_device(zone_dev.id)
                    return

                # Next section of logic just creates a Zone  image folder
                # with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
                zone_image_folder = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/{zone_dev.address}"
                if not os.path.exists(zone_image_folder):
                    try:
                        self.mkdir_with_mode(zone_image_folder)
                    except OSError as exception_error:  # Handles the situation where the folder gets created by image processing in-between the check and mkdir statements!
                        if exception_error.errno != errno.EEXIST:  # TODO: CHECK THIS OUT FOR PYTHON 3
                            pass
                        pass
                else:
                    file_list = os.listdir(zone_image_folder)
                    for file_name in file_list:
                        if file_name.endswith(".txt"):
                            os.remove(os.path.join(zone_image_folder, file_name))

                zone_id_file_name = f"{zone_image_folder}/_{zone_dev.name.upper()}.txt"
                zone_id_file = open(zone_id_file_name, 'w')
                zone_id_file.write(f"{zone_dev.name}")
                zone_id_file.close()

                self.update_roon_zone_device(zone_dev.id, zone_id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                output_id = output_dev.pluginProps.get('roonOutputId', '')

                if output_dev.address[0:4] != 'OUT-':
                    address_number = self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS].pop(0)
                    if address_number[0:1] == '_':
                        address_number = address_number[1:2]
                    address = f"OUT-{address_number}"
                    output_dev_plugin_props = output_dev.pluginProps
                    output_dev_plugin_props["address"] = address

                    self.globals[ROON][MAP_OUTPUT][address_number] = dict()
                    self.globals[ROON][MAP_OUTPUT][address_number][INDIGO_DEV_ID] = output_dev.id
                    self.globals[ROON][MAP_OUTPUT][address_number][ROON_OUTPUT_ID] = output_id
                    output_dev.replacePluginPropsOnServer(output_dev_plugin_props)
                    return

                if output_id not in self.globals[ROON][OUTPUTS]:
                    key_value_list = [
                        {'key': 'output_connected', 'value': False},
                        {'key': 'output_status', 'value': 'disconnected'},
                    ]
                    output_dev.updateStatesOnServer(key_value_list)
                    output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    return

                self.update_roon_output_device(output_dev.id, output_id)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    # def deviceStopComm(self, dev, deviceBeingDeleted=False):  TODO: What is this?

    def deviceStopComm(self, dev):
        try:
            if dev.id in self.globals[ROON][INDIGO_DEVICE_BEING_DELETED]:
                device_being_deleted_address = self.globals[ROON][INDIGO_DEVICE_BEING_DELETED][dev.id]
                device_being_deleted = True
                del self.globals[ROON][INDIGO_DEVICE_BEING_DELETED][dev.id]

                if dev.deviceTypeId == 'roonZone':
                    self.logger.debug(f"'deviceStopComm' Deleted Roon Zone device Address: {device_being_deleted_address}")
                    if device_being_deleted_address[0:5] == 'ZONE-':
                        # device_being_deleted_address = e.g. 'ZONE-A-2' which gives 'A' or ZONE-BC-3 which gives 'BC'
                        zone_alpha = device_being_deleted_address.split('-')[1]
                        if len(zone_alpha) == 1:
                            zone_alpha = f" {zone_alpha}"
                        self.globals[ROON][AVAILABLE_ZONE_ALPHAS].append(zone_alpha)  # Make Alpha available again
                        self.globals[ROON][AVAILABLE_ZONE_ALPHAS].sort()

                        self.logger.debug(f"Roon 'availableZoneAlphas':\n{self.globals[ROON][AVAILABLE_ZONE_ALPHAS]}\n")

                elif dev.deviceTypeId == 'roonOutput':
                    self.logger.debug(f"'deviceStopComm' Deleted Roon Output device Address: {device_being_deleted_address}")
                    if device_being_deleted_address[0:7] == 'OUTPUT-':
                        # device_being_deleted_address = e.g. 'OUTPUT-2' which gives '2'
                        output_number = device_being_deleted_address.split('-')[1]
                        if len(output_number) == 1:
                            output_number = f" {output_number}"
                        # Make Number available again
                        self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS].append(output_number)
                        self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS].sort()

                        self.logger.debug(f"Roon 'availableOutputNumbers':\n{self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS]}\n")
            else:
                device_being_deleted = False

            if dev.deviceTypeId == 'roonZone':
                zone_dev = dev
                for zoneUniqueIdentityKey, devId in list(self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID].items()):
                    if devId == zone_dev.id:
                        del self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                if not device_being_deleted:
                    self.disconnect_roon_zone_device(zone_dev.id)

            elif dev.deviceTypeId == 'roonOutput':
                output_dev = dev
                for output_id, devId in list(self.globals[ROON][OUTPUT_ID_TO_DEV_ID].items()):
                    if devId == output_dev.id:
                        del self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id]
                if not device_being_deleted:
                    self.disconnect_roon_output_device(output_dev.id)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceUpdated(self, origDev, newDev):
        # TODO: IS THIS METHOD NEEDED?
        try:
            if (newDev.deviceTypeId == 'roonController' and
                    newDev.configured and
                    newDev.id in self.globals[ROON] and
                    self.globals[ROON][newDev.id][DEVICE_STARTED]):  # IGNORE THESE UPDATES TO AVOID LOOP!!!
                pass

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            indigo.PluginBase.deviceUpdated(self, origDev, newDev)

    def didDeviceCommPropertyChange(self, orig_dev, new_dev):  # noqa [May be static]
        if orig_dev.deviceTypeId == 'roonZone':
            if 'dynamicGroupedZoneRename' in orig_dev.pluginProps:
                if orig_dev.pluginProps['dynamicGroupedZoneRename'] != new_dev.pluginProps['dynamicGroupedZoneRename']:
                    return True
        return False

    def getActionConfigUiValues(self, plugin_props, type_id, action_id):
        try:
            error_dict = indigo.Dict()
            values_dict = plugin_props

            if type_id == "groupOutputs":  # <Action id="groupOutputs" deviceFilter="self.roonOutput" uiPath="DeviceActions" alwaysUseInDialogHeightCalc="true">

                roon_output_to_group_to_name = indigo.devices[action_id].name
                values_dict["roonOutputToGroupTo"] = roon_output_to_group_to_name

            return values_dict, error_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def getDeviceConfigUiValues(self, plugin_props, type_id, dev_id):
        try:
            if type_id == 'roonZone':
                if 'roonZoneUniqueIdentityKey' not in plugin_props:
                    plugin_props['roonZoneUniqueIdentityKey'] = "-"
                if 'autoNameNewRoonZone' not in plugin_props:
                    plugin_props['autoNameNewRoonZone'] = True
                if 'dynamicGroupedZoneRename' not in plugin_props:
                    plugin_props['dynamicGroupedZoneRename'] = self.globals[CONFIG][DYNAMIC_GROUPED_ZONES_RENAME]
            elif type_id == 'roonOutput':
                if 'roonOutputId' not in plugin_props:
                    plugin_props['roonOutputId'] = "-"

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            return super(Plugin, self).getDeviceConfigUiValues(plugin_props, type_id, dev_id)

    def getPrefsConfigUiValues(self):
        prefs_config_ui_values = self.pluginPrefs

        if "roonVariableFolderName" not in prefs_config_ui_values:
            prefs_config_ui_values["roonVariableFolderName"] = "Roon"

        if "roonCoreIpAddress" not in prefs_config_ui_values:
            prefs_config_ui_values["roonCoreIpAddress"] = "127.0.0.1"
        if "roonCorePort" not in prefs_config_ui_values:
            prefs_config_ui_values["roonCorePort"] = "9300"
        if "autoCreateDevices" not in prefs_config_ui_values:
            prefs_config_ui_values["autoCreateDevices"] = False
        if "roonDeviceFolderName" not in prefs_config_ui_values:
            prefs_config_ui_values["roonDeviceFolderName"] = "Roon"
        if "dynamicGroupedZonesRename" not in prefs_config_ui_values:
            prefs_config_ui_values["dynamicGroupedZonesRename"] = True

        return prefs_config_ui_values

    def shutdown(self):
        self.logger.debug("Shutdown called")

        self.logger.info("'Roon Controller' Plugin shutdown complete")

    def startup(self):
        try:
            # indigo.devices.subscribeToChanges()  # TODO: Don't think this is needed!

            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonOutput':
                    output_number = dev.address.split('-')[1]  # dev.address = e.g. 'OUTPUT-6' which gives '6'
                    if len(output_number) == 1:
                        output_number = f" {output_number}"
                    output_id = dev.pluginProps.get('roonOutputId', '')
                    if output_id != '':
                        self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id] = dev.id
                    try:
                        self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS].remove(output_number)
                    except ValueError:
                        self.logger.error(f"Roon Output '{dev.name}' device with address '{dev.address}' invalid:"
                                          "  Address number '{output_number}' already allocated!:\n{self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS]}\n")

                    self.disconnect_roon_output_device(dev.id)

                elif dev.deviceTypeId == 'roonZone':
                    zone_alpha = dev.address.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A'
                    if len(zone_alpha) == 1:
                        zone_alpha = f" {zone_alpha}"
                    zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                    if zone_unique_identity_key != '':
                        self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key] = dev.id
                    try:
                        self.globals[ROON][AVAILABLE_ZONE_ALPHAS].remove(zone_alpha)
                    except ValueError:
                        self.logger.error(f"Roon Zone '{dev.name}' device with address '{dev.address}' invalid:"
                                          "  Address letter '{zone_alpha}' already allocated!:\n{self.globals[ROON][AVAILABLE_ZONE_ALPHAS]}\n")
                    self.disconnect_roon_zone_device(dev.id)

            # Remove image  files for deleted or renamed Indigo Roon Zone devices
            dir_list = [d for d in os.listdir(self.globals[ROON][PLUGIN_PREFS_FOLDER]) if os.path.isdir(
                os.path.join(self.globals[ROON][PLUGIN_PREFS_FOLDER], d))]
            for dir_name in dir_list:
                dir_alpha = dir_name.split('-')[1]  # dev.address = e.g. 'ZONE-A-2' which gives 'A' or 'ZONE-CD-1' which gives 'CD'
                if len(dir_alpha) == 1:
                    dir_alpha = f" {dir_alpha}"
                if dir_alpha in self.globals[ROON][AVAILABLE_ZONE_ALPHAS]:
                    dir_path_and_name = os.path.join(self.globals[ROON][PLUGIN_PREFS_FOLDER], dir_name)
                    file_list = os.listdir(dir_path_and_name)
                    for fileName in file_list:
                        os.remove(os.path.join(dir_path_and_name, fileName))
                    os.rmdir(dir_path_and_name)

            self.logger.threaddebug(f"Roon 'availableOutputNumbers':\n{self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS]}\n")
            self.logger.threaddebug(f"Roon 'availableZoneAlphas':\n{self.globals[ROON][AVAILABLE_ZONE_ALPHAS]}\n")

            self.globals[ROON][TOKEN] = None

            self.globals[ROON][TOKEN_FILE] = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/roon_token.txt"

            if os.path.isfile(self.globals[ROON][TOKEN_FILE]):
                with open(self.globals[ROON][TOKEN_FILE]) as f:
                    self.globals[ROON][TOKEN] = f.read()

            self.logger.debug(f"'Roon Controller' token [0]: {self.globals[ROON][TOKEN]}")

            if self.globals[CONFIG][ROON_CORE_IP_ADDRESS] == '':
                self.logger.error("'Roon Controller' has no Roon Core IP Address specified in Plugin configuration"
                                  " - correct and then restart plugin.")
                return False

            self.globals[ROON][API] = RoonApi(self.globals[ROON][EXTENSION_INFO], self.globals[ROON][TOKEN],
                                                  self.globals[CONFIG][ROON_CORE_IP_ADDRESS], self.globals[CONFIG][ROON_CORE_PORT])
            self.globals[ROON][API].register_state_callback(self.process_roon_callback_state)
            # self.globals[ROON][API].register_queue_callback(self.process_roon_callback_queue)

            # self.globals[ROON][API].register_volume_control('Indigo', 'Indigo', self.process_roon_volume_control)

            self.logger.debug(f"'Roon Controller' token [1]: {self.globals[ROON][TOKEN]}")

            self.globals[ROON][TOKEN] = self.globals[ROON][API].token
            self.logger.debug(f"'Roon Controller' token [2]: {self.globals[ROON][TOKEN]}")

            if self.globals[ROON][TOKEN]:
                with open(self.globals[ROON][TOKEN_FILE], "w") as f:
                    f.write(self.globals[ROON][TOKEN])

            self.globals[ROON][ZONES] = copy.deepcopy(self.globals[ROON][API].zones)
            self.globals[ROON][OUTPUTS] = copy.deepcopy(self.globals[ROON][API].outputs)

            self.process_outputs(self.globals[ROON][OUTPUTS])
            self.process_zones(self.globals[ROON][ZONES])

            # self.print_known_zones_summary('INITIALISATION')

            self.logger.info("'Roon Controller' initialization complete.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def stopConcurrentThread(self):
        self.logger.debug("Thread shutdown called")

        self.stopThread = True

    def validateActionConfigUi(self, values_dict, type_id, actionId):
        try:
            self.logger.debug("Validate Action Config UI: type_id = '{type_id}', actionId = '{actionId}', values_dict =\n{values_dict}\n")

            if type_id == "qwerty":
                pass
            return True, values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):  # Validate Roon device
        try:
            if type_id == 'roonZone':
                valid = False
                if 'roonZoneUniqueIdentityKey' in values_dict and len(values_dict['roonZoneUniqueIdentityKey']) > 5:
                    valid = True
                if not valid:
                    error_dict = indigo.Dict()
                    error_dict["roonZoneUniqueIdentityKey"] = "No Roon Zone selected or available"
                    error_dict["showAlertText"] = "You must select an available Roon Zone to be able to create the Roon Zone device."
                    return False, values_dict, error_dict

            elif type_id == 'roonOutput':
                valid = False
                if 'roonOutputId' in values_dict and len(values_dict['roonOutputId']) > 5:
                    valid = True
                if not valid:
                    error_dict = indigo.Dict()
                    error_dict["roonOutputId"] = "No Roon Output selected or available"
                    error_dict["showAlertText"] = "You must select an available Roon Output to be able to create the Roon Output device."
                    return False, values_dict, error_dict

            return True, values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validatePrefsConfigUi(self, values_dict):
        try:
            ip_address = values_dict.get('roonCoreIpAddress', '')

            try:
                socket.inet_aton(ip_address)
            except:
                error_dict = indigo.Dict()
                error_dict["roonCoreIpAddress"] = "Roon Core IP Address is invalid"
                error_dict["showAlertText"] = ("You must enter a valid Roon Core IP Address"
                                               " to be able to connect to the Roon Core.")
                return False, values_dict, error_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            return True, values_dict

    def auto_create_output_device(self, output_id):
        try:
            self.logger.debug(f"Roon 'availableOutputNumbers':\n{self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS]}\n")

            address_number = self.globals[ROON][AVAILABLE_OUTPUT_NUMBERS].pop(0)
            if address_number[0:1] == ' ':
                address_number = address_number[1:2]
            address = f"OUT-{address_number}"

            output_name = f"Roon Output - {self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}"

            output_dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                          address=address,
                          name=output_name,
                          description='Roon Output',
                          pluginId="com.autologplugin.indigoplugin.rooncontroller",
                          deviceTypeId="roonOutput",
                          props={"roonOutputId": output_id,
                                 "roonOutputIdUi": output_id,
                                 "autoNameNewRoonOutput": True},
                          folder=self.globals[CONFIG][ROON_DEVICE_FOLDER_ID]))

            self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id] = output_dev.id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def auto_create_zone_device(self, zone_id, zoneUniqueIdentityKey):
        try:
            self.logger.debug(f"Roon 'availableZoneAlphas':\n{self.globals[ROON][AVAILABLE_ZONE_ALPHAS]}\n")

            outputCount = self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]
            addressAlpha = self.globals[ROON][AVAILABLE_ZONE_ALPHAS].pop(0)
            if addressAlpha[0:1] == ' ':
                addressAlpha = addressAlpha[1:2]
            if outputCount > 0:
                address = f"ZONE-{addressAlpha}-{outputCount}"
            else:
                address = f"ZONE-{addressAlpha}"

            zone_name = f"{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}"

            if outputCount == 0:
                device_name = f"Roon Zone - {zone_name}"
            else:
                temp_zone_name = self.globals[ROON][ZONES][zone_id][OUTPUTS][1][DISPLAY_NAME]
                for i in range(2, outputCount + 1):
                    temp_zone_name = f"{temp_zone_name} + {self.globals[ROON][ZONES][zone_id][OUTPUTS][i][DISPLAY_NAME]}"
                device_name = f"Roon Zone - {temp_zone_name}"

            self.logger.debug(f"'auto_create_zone_device' - Creating Indigo Zone Device with Name: '{device_name}', Zone Name: '{zone_name}',\nZone Unique Identity Key: '{zoneUniqueIdentityKey}'")

            defaultdynamicGroupedZonesRename = self.globals[CONFIG][DYNAMIC_GROUPED_ZONES_RENAME]

            zone_dev = (indigo.device.create(
                        protocol=indigo.kProtocol.Plugin,
                        address=address,
                        name=device_name,
                        description='Roon Zone',
                        pluginId="com.autologplugin.indigoplugin.rooncontroller",
                        deviceTypeId="roonZone",
                        props={"roonZoneName": zone_name,
                               "roonZoneId": zone_id,
                               "roonZoneUniqueIdentityKey": zoneUniqueIdentityKey,
                               "roonZoneUniqueIdentityKeyUi": zoneUniqueIdentityKey,
                               "autoNameNewRoonZone": True,
                               "dynamicGroupedZoneRename": defaultdynamicGroupedZonesRename},
                        folder=self.globals[CONFIG][ROON_DEVICE_FOLDER_ID]))

            self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey] = zone_dev.id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def convert_output_id_list_to_string(self, roonZoneOutputsList):
        try:
            outputs_list_string = ""

            if type(roonZoneOutputsList) is list:
                for outputId in roonZoneOutputsList:
                    if outputs_list_string == '':
                        outputs_list_string = f"{outputId}"
                    else:
                        outputs_list_string = f"{outputs_list_string}#{outputId}"

                return outputs_list_string
            else:
                return roonZoneOutputsList

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def disconnect_roon_output_device(self, roonOutputDevId):
        try:
            output_dev = indigo.devices[roonOutputDevId]
            key_value_list = [
                {'key': 'output_connected', 'value': False},
                {'key': 'output_status', 'value': 'disconnected'},
                {'key': 'output_id', 'value': ''},
                # {'key': 'display_name', 'value': ''},  # < TEST LEAVING DISPLAY NAME UNALTERED
                {'key': 'zone_id', 'value': ''},
                {'key': 'source_control_1_status', 'value': ''},
                {'key': 'source_control_1_display_name', 'value': ''},
                {'key': 'source_control_1_control_key', 'value': ''},
                {'key': 'source_control_1_supports_standby', 'value': ''},
                {'key': 'volume_hard_limit_min', 'value': 0},
                {'key': 'volume_min', 'value': 0},
                {'key': 'volume_is_muted', 'value': False},
                {'key': 'volume_max', 'value': 0},
                {'key': 'volume_value', 'value': 0},
                {'key': 'volume_step', 'value': 1},
                {'key': 'volume_hard_limit_max', 'value': 0},
                {'key': 'volume_soft_limit', 'value': 0},
                {'key': 'volume_type', 'value': 'number'},
                {'key': 'can_group_with_output_id_1', 'value': ''},
                {'key': 'can_group_with_output_id_2', 'value': ''},
                {'key': 'can_group_with_output_id_3', 'value': ''},
                {'key': 'can_group_with_output_id_4', 'value': ''},
                {'key': 'can_group_with_output_id_5', 'value': ''}]

            output_dev.updateStatesOnServer(key_value_list)
            output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def disconnect_roon_zone_device(self, roonZoneDevId):
        try:
            zone_dev = indigo.devices[roonZoneDevId]
            key_value_list = [
                {'key': 'zone_connected', 'value': False},
                {'key': 'zone_status', 'value': 'disconnected'},
                {'key': 'zone_id', 'value': ''},
                {'key': 'display_name', 'value': ''},
                {'key': 'auto_radio', 'value': False},
                {'key': 'shuffle', 'value': False},
                {'key': 'loop', 'value': False},
                {'key': 'number_of_outputs', 'value': 0},
                {'key': 'output_1_id', 'value': ''},
                {'key': 'output_2_id', 'value': ''},
                {'key': 'output_3_id', 'value': ''},
                {'key': 'output_4_id', 'value': ''},
                {'key': 'output_5_id', 'value': ''},
                {'key': 'number_of_artist_image_keys', 'value': 0},
                {'key': 'artist_image_Key_1_id', 'value': ''},
                {'key': 'artist_image_Key_2_id', 'value': ''},
                {'key': 'artist_image_Key_3_id', 'value': ''},
                {'key': 'artist_image_Key_4_id', 'value': ''},
                {'key': 'artist_image_Key_5_id', 'value': ''},
                {'key': 'image_key', 'value': ''},
                {'key': 'one_line_1', 'value': ''},
                {'key': 'two_line_1', 'value': ''},
                {'key': 'two_line_2', 'value': ''},
                {'key': 'three_line_1', 'value': ''},
                {'key': 'three_line_2', 'value': ''},
                {'key': 'three_line_3', 'value': ''},
                {'key': 'length', 'value': 0},
                {'key': 'ui_length', 'value': '0:00'},
                {'key': 'seek_position', 'value': 0},
                {'key': 'remaining', 'value': 0},
                {'key': 'ui_remaining', 'value': '0:00'},
                {'key': 'is_previous_allowed', 'value': False},
                {'key': 'is_pause_allowed', 'value': False},
                {'key': 'is_seek_allowed', 'value': False},
                {'key': 'state', 'value': False},
                {'key': 'is_play_allowed', 'value': False},
                {'key': 'is_next_allowed', 'value': False}]

            zone_dev.updateStatesOnServer(key_value_list)
            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def list_roon_output_ids(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            outputs_list = list()

            allocated_output_ids = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonOutput':
                    roonOutputId = dev.pluginProps.get('roonOutputId', '')
                    allocated_output_ids.append(roonOutputId)
                    if dev.id == targetId and roonOutputId != '':
                        if dev.states['output_status'] == 'connected':
                            # Append self
                            outputs_list.append((roonOutputId,
                                                 self.globals[ROON][OUTPUTS][roonOutputId][DISPLAY_NAME]))
                        else:
                            display_name = dev.states['display_name']
                            if display_name != '':
                                display_name = display_name + ' '
                            # Append self
                            outputs_list.append((roonOutputId, f"{display_name} [Output disconnected]"))

            for output_id in self.globals[ROON][OUTPUTS]:
                if output_id not in allocated_output_ids:
                    outputs_list.append((self.globals[ROON][OUTPUTS][output_id][OUTPUT_ID],
                                         self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]))

            if len(outputs_list) == 0:
                outputs_list.append(('-', '-- No Available Outputs --'))
                return outputs_list
            else:
                outputs_list.append(('-', '-- Select Output --'))

            return sorted(outputs_list, key=lambda output_name: output_name[1].lower())   # sort by Output name

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def list_roon_zone_unique_identity_keys(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            self.logger.debug(f"TYPE_ID = {type_id}, TARGET_ID = {targetId}")

            allocatedRoonZoneUniqueIdentityKeys = []
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == 'roonZone' and targetId != dev.id:
                    zone_unique_identity_key = dev.pluginProps.get('roonZoneUniqueIdentityKey', '')
                    if zone_unique_identity_key != '':
                        allocatedRoonZoneUniqueIdentityKeys.append(zone_unique_identity_key)

            zone_unique_identity_keys_list = list()

            for zone_id in self.globals[ROON][ZONES]:
                if self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY] not in allocatedRoonZoneUniqueIdentityKeys:
                    zone_unique_identity_keys_list.append((self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY], self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]))

            if len(zone_unique_identity_keys_list) == 0:
                zone_unique_identity_keys_list.append(('-', '-- No Available Zones --'))
                return zone_unique_identity_keys_list
            else:
                zone_unique_identity_keys_list.append(('-', '-- Select Zone --'))

            return sorted(zone_unique_identity_keys_list, key=lambda zone_name: zone_name[1].lower())   # sort by Zone name

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def mkdir_with_mode(self, directory):
        try:
            # Forces Read | Write on creation so that the plugin can delete the folder id required
            if not os.path.isdir(directory):
                oldmask = os.umask(000)
                os.makedirs(directory, 0o777)
                os.umask(oldmask)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def now_playing_variables(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            myArray = []
            for var in indigo.variables:
                if self.globals[CONFIG][ROON_VARIABLE_FOLDER_ID] == 0:
                    myArray.append((var.id, var.name))
                else:
                    if var.folderId == self.globals[CONFIG][ROON_VARIABLE_FOLDER_ID]:
                        myArray.append((var.id, var.name))

            myArraySorted = sorted(myArray, key=lambda varname: varname[1].lower())   # sort by variable name
            myArraySorted.insert(0, (0, 'NO NOW PLAYING VARIABLE'))
            myArraySorted.insert(0, (-1, '-- Select Now Playing Variable --'))

            return myArraySorted

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def print_known_outputs_summary(self, title):
        try:
            if self.globals[CONFIG][PRINT_OUTPUTS_SUMMARY]:
                logout = f"\n#################### {title} ####################\n"
                for output_id in self.globals[ROON][OUTPUTS]:
                    if 'display_name' in self.globals[ROON][OUTPUTS][output_id]:
                        outputdisplay_name = self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]
                    else:
                        outputdisplay_name = "NONE"
                    logout = logout + f"Output '{outputdisplay_name}' - Output ID = '{output_id}'"
                logout = logout + '####################\n'
                self.logger.debug(logout)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def print_known_zones_summary(self, title):
        try:
            if self.globals[CONFIG][PRINT_ZONES_SUMMARY]:
                logout = f"\n#################### {title} ####################"
                logout = logout + "\nInternal Zone table\n"
                for zone_id in self.globals[ROON][ZONES]:
                    if 'display_name' in self.globals[ROON][ZONES][zone_id]:
                        zone_display_name = self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]
                    else:
                        zone_display_name = "NONE"
                    logout = logout + f"\nZone '{zone_display_name}' - Zone ID = '{zone_id}'"
                logout = logout + "\nIndigo Zone Devices\n"
                for dev in indigo.devices.iter("self"):
                    if dev.deviceTypeId == 'roonZone':
                        zone_id = dev.pluginProps.get('roonZoneId', '-- Zone ID not set!')
                        logout = logout + f"\nIndigo Device '{dev.name}' - Zone ID = '{zone_id}', Status =  '{dev.states['zone_status']}'"
                logout = logout + "\n####################\n"
                self.logger.info(logout)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def print_output(self, output_id):
        try:
            outputPrint = "\n\nROON OUTPUT PRINT\n"
            outputPrint = outputPrint + f"\nOutput: {self.globals[ROON][OUTPUTS][output_id][OUTPUT_ID]}"
            outputPrint = outputPrint + f"\n    Display Name: {self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}"
            outputPrint = outputPrint + f"\n    Zone Id: {self.globals[ROON][OUTPUTS][output_id][ZONE_ID]}"

            if 'source_controls' in self.globals[ROON][OUTPUTS][output_id]:
                outputPrint = outputPrint + f"\n    Source Controls: Count = {self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS_COUNT]}"
                for key2, value2 in list(self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS].items()):
                    key2Int = int(key2)
                    outputPrint = outputPrint + f"\n        Source Controls '{key2}'"
                    outputPrint = outputPrint + f"\n            Status: { self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][key2Int][STATUS]}"
                    outputPrint = outputPrint + f"\n            Display Name: { self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][key2Int][DISPLAY_NAME]}"
                    outputPrint = outputPrint + f"\n            Control Key: {self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][key2Int][CONTROL_KEY]}"
                    outputPrint = outputPrint + f"\n            Supports Standby: {self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][key2Int][SUPPORTS_STANDBY]}"

            if 'volume' in self.globals[ROON][OUTPUTS][output_id] and len(
                    self.globals[ROON][OUTPUTS][output_id][VOLUME]) > 0:
                outputPrint = outputPrint + "\n    Volume:"
                outputPrint = outputPrint + f"\n        Hard Limit Min: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MIN]}"
                outputPrint = outputPrint + f"\n        Min: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MIN]}"
                outputPrint = outputPrint + f"\n        Is Muted: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_IS_MUTED]}"
                outputPrint = outputPrint + f"\n        Max: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MAX]}"
                outputPrint = outputPrint + f"\n        Value: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_VALUE]}"
                outputPrint = outputPrint + f"\n        Step: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_STEP]}"
                outputPrint = outputPrint + f"\n        Hard Limit Max: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MAX]}"
                outputPrint = outputPrint + f"\n        Soft Limit: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_SOFT_LIMIT]}"
                outputPrint = outputPrint + f"\n        Type: {self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_TYPE]}"

            outputPrint = outputPrint + f"\n    Can Group With Output Ids: Count = {self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS_COUNT]}"
            for key2, value2 in list(self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS].items()):
                key2Int = int(key2)
                outputPrint = outputPrint + f"\n        Output Id [{key2}]: {self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][key2Int]}"

            self.logger.debug(outputPrint)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def print_zone(self, zone_id):
        try:
            zone_print = f"\n\nROON ZONE PRINT: '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}'\n"
            zone_print = zone_print         + f"\nZone: {self.globals[ROON][ZONES][zone_id][ZONE_ID]}"
            zone_print = zone_print         + f"\n    Queue Items Remaining: {self.globals[ROON][ZONES][zone_id][QUEUE_ITEMS_REMAINING]}"
            zone_print = zone_print         + f"\n    Queue Time Remaining: {self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING]}"
            zone_print = zone_print         + f"\n    Display Name: {self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}"
            zone_print = zone_print         + "\n    Settings:"
            zone_print = zone_print         + f"\n        Auto Radio: {self.globals[ROON][ZONES][zone_id][SETTINGS][AUTO_RADIO]}"
            zone_print = zone_print         + f"\n        Shuffle: {self.globals[ROON][ZONES][zone_id][SETTINGS][SHUFFLE]}"
            zone_print = zone_print         + f"\n        Loop: {self.globals[ROON][ZONES][zone_id][SETTINGS][LOOP]}"
            zone_print = zone_print         + f"\n    zone_id Unique Identity Key: {self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]}"
            zone_print = zone_print         + f"\n    Outputs: Count = {self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]}"

            for key, value in list(self.globals[ROON][ZONES][zone_id][OUTPUTS].items()):
                keyInt = int(key)
                zone_print = zone_print     + f"\n        Output '{key}'"
                zone_print = zone_print     + f"\n            Output Id: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][OUTPUT_ID]}"
                zone_print = zone_print     + f"\n            Display Name: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][DISPLAY_NAME]}"
                zone_print = zone_print     + f"\n            Zone Id: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][ZONE_ID]}"

                zone_print = zone_print     + f"\n            Source Controls: Count = {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS_COUNT]}"
                for key2, value2 in list(self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS].items()):
                    key2Int = int(key2)
                    zone_print = zone_print + f"\n                Source Controls '{key2}'"
                    zone_print = zone_print + f"\n                    Status: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS][key2Int][STATUS]}"
                    zone_print = zone_print + f"\n                    Display Name: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS][key2Int][DISPLAY_NAME]}"
                    zone_print = zone_print + f"\n                    Control Key: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS][key2Int][CONTROL_KEY]}"
                    zone_print = zone_print + f"\n                    Supports Standby: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][SOURCE_CONTROLS][key2Int][SUPPORTS_STANDBY]}"
                zone_print = zone_print     + "\n            Volume:"
                zone_print = zone_print     + f"\n                Hard Limit Min: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_HARD_LIMIT_MIN]}"
                zone_print = zone_print     + f"\n                Min: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_MIN]}"
                zone_print = zone_print     + f"\n                Is Muted: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_IS_MUTED]}"
                zone_print = zone_print     + f"\n                Max: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_MAX]}"
                zone_print = zone_print     + f"\n                Value: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_VALUE]}"
                zone_print = zone_print     + f"\n                Step: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_STEP]}"
                zone_print = zone_print     + f"\n                Hard Limit Max: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_HARD_LIMIT_MAX]}"
                zone_print = zone_print     + f"\n                Soft Limit: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_SOFT_LIMIT]}"
                zone_print = zone_print     + f"\n                Type: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][VOLUME][VOLUME_TYPE]}"

                zone_print = zone_print     + f"\n            Can Group With Output Ids: Count = {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][CAN_GROUP_WITH_OUTPUT_IDS_COUNT]}"
                for key2, value2 in list(self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][CAN_GROUP_WITH_OUTPUT_IDS].items()):
                    key2Int = int(key2)
                    zone_print = zone_print + f"\n                Output Id [{key2}]: {self.globals[ROON][ZONES][zone_id][OUTPUTS][keyInt][CAN_GROUP_WITH_OUTPUT_IDS][key2Int]}"

            zone_print = zone_print         + "\n    Now Playing:"
            if 'artist_image_keys' in self.globals[ROON][ZONES][zone_id][NOW_PLAYING]:
                zone_print = zone_print     + f"\n        Artist Image Keys: Count = {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS_COUNT]}"
                for key, value in list(self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS].items()):
                    keyInt = int(key)
                    zone_print = zone_print + f"\n            Artist Image Key: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][keyInt]}"

            if 'image_key' in self.globals[ROON][ZONES][zone_id][NOW_PLAYING]:
                zone_print = zone_print     + f"\n        Image Key: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY]}"
            if 'length' in self.globals[ROON][ZONES][zone_id][NOW_PLAYING]:
                zone_print = zone_print     + f"\n        Length: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH]}"
            zone_print = zone_print         + f"\n        Seek Position: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION]}"
            zone_print = zone_print         +  "\n        One Line:"
            zone_print = zone_print         + f"\n            Line 1: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1]}"
            zone_print = zone_print         +  "\n        Two Line:"
            zone_print = zone_print         + f"\n            Line 1: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_1]}"
            zone_print = zone_print         + f"\n            Line 2: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_2]}"
            zone_print = zone_print         +  "\n        Three Line:"
            zone_print = zone_print         + f"\n            Line 1: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1]}"
            zone_print = zone_print         + f"\n            Line 2: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2]}"
            zone_print = zone_print         + f"\n            Line 3: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3]}"

            zone_print = zone_print         + f"\n    Is Previous Allowed: {self.globals[ROON][ZONES][zone_id][IS_PREVIOUS_ALLOWED]}"
            zone_print = zone_print         + f"\n    Is Pause Allowed: {self.globals[ROON][ZONES][zone_id][IS_PAUSE_ALLOWED]}"
            zone_print = zone_print         + f"\n    Is Seek Allowed: {self.globals[ROON][ZONES][zone_id][IS_SEEK_ALLOWED]}"
            zone_print = zone_print         + f"\n    State: {self.globals[ROON][ZONES][zone_id][STATE]}"
            zone_print = zone_print         + f"\n    Is Play Allowed: {self.globals[ROON][ZONES][zone_id][IS_PLAY_ALLOWED]}"
            zone_print = zone_print         + f"\n    Is Next Allowed: {self.globals[ROON][ZONES][zone_id][IS_NEXT_ALLOWED]}"

            self.logger.debug(zone_print)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def print_zone_summary(self, pluginAction):
        try:
            self.print_known_zones_summary('PROCESS PRINT ZONE SUMMARY ACTION')

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_group_outputs(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(f"'process_group_outputs' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as no Output device specified in Action.")
                return

            if not output_dev.states['output_connected']:
                self.logger.error(f"'process_group_outputs' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev.name}' is disconnected.")
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(f"'process_group_outputs' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev.name}' is not connected to the Roon Core.")
                return

            forceGroupAction = bool(plugin_action.props.get('forceGroupAction', True))

            output_dev_plugin_props = output_dev.pluginProps
            output_id = output_dev_plugin_props.get('roonOutputId', '')

            outputs_to_group_list = [output_id]

            output_ids = plugin_action.props['roonOutputsList']

            for output_id in output_ids:
                outputs_to_group_list.append(output_id.strip())

            for output_id_to_group in outputs_to_group_list:
                output_dev_to_group = indigo.devices[self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id_to_group]]

                if not output_dev_to_group.states['output_connected']:
                    self.logger.error(f"'process_group_outputs' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output to group '{output_dev_to_group.name}' is disconnected.")
                    return

                output_id = output_dev.states['output_id']
                if output_id == '':
                    self.logger.debug(f"'process_group_outputs' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev_to_group.name}' is not connected to the Roon Core.")
                    return

            if len(outputs_to_group_list) > 0:
                self.globals[ROON][API].group_outputs(outputs_to_group_list)

        except Exception as exception_error:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            detailed_exception_error = f"Output Device '{output_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_image(self, image_type, image_suffix, zone_dev, image_key):
        try:
            # Next section of logic just creates a Zone  image folder with a dummy text file with the display name of the Zone to aid in viewing the image folder structure
            zone_image_folder = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/{zone_dev.address}"
            if not os.path.exists(zone_image_folder):
                try:
                    self.mkdir_with_mode(zone_image_folder)
                except FileExistsError:  # Handles the situation where the folder gets created by device start processing in between the check and mkdifr statements!
                    pass

            image_name = ['Artist_Image', 'Album_Image'][image_type]
            if image_suffix != '':
                image_name = f"{image_name}_{image_suffix}"
            set_default_image = True
            if image_key != '':
                image_url = self.globals[ROON][API].get_image(image_key, scale="fill")
                work_file = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/{zone_dev.address}/temp.jpg"
                image_request = requests.get(image_url)
                if image_request.status_code == 200:
                    try:
                        with open(work_file, 'wb') as f:
                            f.write(image_request.content)
                        image_to_process = Image.open(work_file)
                        output_image_file = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/{zone_dev.address}/{image_name}.png"
                        image_to_process.save(output_image_file)
                        try:
                            os.remove(work_file)
                        except:  # Not sure why this doesn't always work!
                            pass
                        set_default_image = False
                    except Exception as exception_error:  # noqa [Too broad exception]
                        # leave as default image if any problem reported but only output debug message
                        self.logger.debug(f"'process_image' [DEBUG ONLY] error detected. Line '{sys.exc_traceback.tb_lineno}' has error: '{exception_error}'")
            if set_default_image:
                default_image_path = f"{self.globals[PLUGIN_INFO][PATH]}/Plugins/Roon.indigoPlugin/Contents/Resources/"
                if image_type == ARTIST:
                    default_image_file = f"{default_image_path}Artist_Image.png"
                elif image_type == ALBUM:
                    default_image_file = f"{default_image_path}Album_Image.png"
                else:
                    default_image_file = f"{default_image_path}Unknown_Image.png"
                output_image_file = f"{self.globals[ROON][PLUGIN_PREFS_FOLDER]}/{zone_dev.address}/{image_name}.png"
                copyfile(default_image_file, output_image_file)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_output(self, output_id, outputData):
        process_output_return_state = False

        try:
            self.globals[ROON][OUTPUTS][output_id] = dict()
            self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS] = dict()
            self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS_COUNT] = 0
            self.globals[ROON][OUTPUTS][output_id][VOLUME] = dict()
            self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS] = dict()

            for outputKey, outputValue in list(outputData.items()):
                if outputKey == 'output_id':
                    self.globals[ROON][OUTPUTS][output_id][OUTPUT_ID] = outputValue
                elif outputKey == 'display_name':
                    self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME] = outputValue
                elif outputKey == 'zone_id':
                    self.globals[ROON][OUTPUTS][output_id][ZONE_ID] = outputValue
                elif outputKey == 'source_controls':
                    sourceControlsCount = 0
                    for sourceControls in outputValue:
                        sourceControlsCount += 1
                        self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][sourceControlsCount] = dict()
                        for sourceControlKey, sourceControlData in list(sourceControls.items()):
                            if sourceControlKey == 'status':
                                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][sourceControlsCount][STATUS] = sourceControlData
                            elif sourceControlKey == 'display_name':
                                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][sourceControlsCount][DISPLAY_NAME] = sourceControlData
                            elif sourceControlKey == 'control_key':
                                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][sourceControlsCount][CONTROL_KEY] = sourceControlData
                            elif sourceControlKey == 'supports_standby':
                                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][sourceControlsCount][SUPPORTS_STANDBY] = bool(sourceControlData)
                    self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS_COUNT] = sourceControlsCount

                elif outputKey == 'volume':
                    for volumeKey, volumeData in list(outputValue.items()):
                        if volumeKey == 'hard_limit_min':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MIN] = volumeData
                        elif volumeKey == 'min':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MIN] = volumeData
                        elif volumeKey == 'is_muted':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_IS_MUTED] = volumeData
                        elif volumeKey == 'max':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MAX] = volumeData
                        elif volumeKey == 'value':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_VALUE] = volumeData
                        elif volumeKey == 'step':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_STEP] = volumeData
                        elif volumeKey == 'hard_limit_max':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MAX] = volumeData
                        elif volumeKey == 'soft_limit':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_SOFT_LIMIT] = volumeData
                        elif volumeKey == 'type':
                            self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_TYPE] = volumeData

                elif outputKey == 'can_group_with_output_ids':
                    canGroupCount = 0
                    for can_group_with_output_id in outputValue:
                        canGroupCount += 1
                        self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][canGroupCount] = can_group_with_output_id
                    self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS_COUNT] = canGroupCount

            if output_id not in self.globals[ROON][OUTPUT_ID_TO_DEV_ID]:
                if self.globals[CONFIG][AUTO_CREATE_DEVICES]:
                    self.auto_create_output_device(output_id)

            if len(self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS]) > 0:
                process_output_return_state = True
            else:
                self.globals[ROON][OUTPUTS][output_id] = dict()
                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS] = dict()
                self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS_COUNT] = 0
                self.globals[ROON][OUTPUTS][output_id][VOLUME] = dict()
                self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS] = dict()
                if output_id in self.globals[ROON][OUTPUT_ID_TO_DEV_ID]:
                    self.disconnect_roon_output_device(self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id])
                process_output_return_state = False

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            return process_output_return_state

    def process_outputs(self, outputs):
        try:
            for output_id, output_data in list(outputs.items()):
                self.process_output(output_id, output_data)
                if self.globals[CONFIG][PRINT_OUTPUT]:
                    self.print_output(output_id)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_outputs_added(self, event, changed_items):
        try:
            for output_id in changed_items:
                if output_id == '1701b9ea8b0814189098501722daf1427ea9':
                    tempOutputs = self.globals[ROON][API].outputs
                    self.logger.debug(f"'process_outputs_changed' - ALL OUTPUTS = \n\n{tempOutputs}\n\n.")

                output_data = copy.deepcopy(self.globals[ROON][API].output_by_output_id(output_id))
                processOutput_successful = self.process_output(output_id, output_data)
                self.logger.debug(f"'process_outputs_added' - Output '{'TEMPORARY DEBUG NAME'}'. Output ID = '{output_id}'\n{output_data}")

                if processOutput_successful:
                    if output_id in self.globals[ROON][OUTPUT_ID_TO_DEV_ID]:
                        roonOutputDevId = self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id]
                        self.update_roon_output_device(roonOutputDevId, output_id)
                        self.logger.debug(
                            f"'process_outputs_added' - Output '{self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}'."
                            f" Indigo Device = '{indigo.devices[roonOutputDevId].name}', Output ID = '{output_id}'")
                    else:
                        self.logger.debug(
                            f"'process_outputs_added' - Output '{self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}' no matching Indigo device. Output ID = '{output_id}'")

                        if self.globals[CONFIG][AUTO_CREATE_DEVICES]:
                            self.auto_create_output_device(output_id)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_outputs_changed(self, event, changed_items):
        try:
            self.logger.debug(f"'process_outputs_changed' - Changed Items = \n\n{changed_items}\n\n.")

            for output_id in changed_items:
                # DEBUG START
                # if output_id == 'hex number':
                #     tempOutputs = self.globals[ROON][API].outputs
                #     self.logger.debug(
                #         f"'process_outputs_changed' - ALL OUTPUTS = \n\n{tempOutputs}\n\n.")
                # DEBUG END

                output_data = copy.deepcopy(self.globals[ROON][API].output_by_output_id(output_id))
                processOutput_successful = self.process_output(output_id, output_data)

                if processOutput_successful:
                    if output_id in self.globals[ROON][OUTPUT_ID_TO_DEV_ID]:
                        roonOutputDevId = self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id]
                        self.update_roon_output_device(roonOutputDevId, output_id)
                        self.logger.debug(f"'process_outputs_changed' - Output '{self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}'."
                                          f" Indigo Device = '{indigo.devices[roonOutputDevId].name}', Output ID = '{ output_id}'\nOutput Data:\n{output_data}\n")
                    else:
                        self.logger.debug(f"'process_outputs_changed' - Output '{self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}'. Output ID = '{output_id}'\n{output_data}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_outputs_removed(self, event, changed_items):
        try:
            self.logger.debug("'OUTPUT REMOVED' INVOKED")
            self.print_known_outputs_summary("PROCESS OUTPUT REMOVED [START]")

            for output_id in changed_items:
                if output_id in self.globals[ROON][OUTPUTS]:
                    output_display_name = "Unknown Output"
                    self.logger.debug(
                        f"'OUTPUT REMOVED' - Output:\n{self.globals[ROON][OUTPUTS][output_id]}")
                    if DISPLAY_NAME in self.globals[ROON][OUTPUTS][output_id]:
                        output_display_name = self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]
                    if output_id in self.globals[ROON][OUTPUT_ID_TO_DEV_ID]:
                        roon_output_dev_id = self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output_id]
                        self.disconnect_roon_output_device(roon_output_dev_id)
                        self.logger.debug(f"'OUTPUT REMOVED' - Output '{output_display_name}'. Indigo Device = '{indigo.devices[roon_output_dev_id].name}', Output ID = '{output_id}'")
                    else:
                        self.logger.debug(f"'OUTPUT REMOVED' - Output '{output_display_name}' no matching Indigo device.")

                del self.globals[ROON][OUTPUTS][output_id]

                self.print_known_outputs_summary('PROCESS OUTPUTS REMOVED [OUTPUT REMOVED]')

            else:
                self.logger.debug(f"'OUTPUT REMOVED' - All Output:\n{self.globals[ROON][OUTPUTS]}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_playback_control(self, invoking_process_name, plugin_action, zone_dev):
        try:
            if zone_dev is None:
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as no Zone device specified in Action.")
                return False

            if not zone_dev.states['zone_connected']:
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{zone_dev.name}' is disconnected.")
                return False

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{zone_dev.name}' is not connected to the Roon Core.")
                return False

            self.globals[ROON][API].playback_control(zone_id, plugin_action.pluginTypeId.lower())

            return True

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_mute(self, plugin_action, zone_dev):
        try:
            if zone_dev is None:
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as no Zone device specified in Action.")
                return

            if not zone_dev.states['zone_connected']:
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{ zone_dev.name}' is disconnected.")
                return

            zone_id = zone_dev.states['zone_id']
            if zone_id == '':
                self.logger.error(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{ zone_dev.name}' is not connected to the Roon Core.")
                return

            if self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT] > 0:
                for output_number in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                    output_id = self.globals[ROON][ZONES][zone_id][OUTPUTS][output_number][OUTPUT_ID]

                    toggle = not self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_IS_MUTED]

                    self.globals[ROON][API].mute(output_id, toggle)

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_mute_all(self, plugin_action, zone_dev):
        try:
            for zone_dev in indigo.devices.iter("self"):
                if zone_dev.deviceTypeId == 'roonZone':

                    if not zone_dev.states['zone_connected']:
                        self.logger.debug(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{zone_dev.name}' is disconnected.")
                        continue

                    zone_id = zone_dev.states['zone_id']
                    if zone_id == '':
                        self.logger.debug(f"Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Zone '{zone_dev.name}' is not connected to the Roon Core.")
                        continue

                    if self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT] > 0:
                        for output_number in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                            output_id = self.globals[ROON][ZONES][zone_id][OUTPUTS][output_number][OUTPUT_ID]
                            self.globals[ROON][API].mute(output_id, True)

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_next(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_next', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' advanced to next track.")

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_pause(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_pause', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' playback paused.")

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_play(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_play', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' playback started.")

        except StandardError as err:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_play_pause(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_play_pause', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' playback toggled.")

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_previous(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_previous', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' gone to start of track or previous track.")

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_stop(self, pluginAction, zone_dev):
        try:
            if self.process_playback_control('process_playback_control_stop', pluginAction, zone_dev):
                self.logger.info(f"Zone '{zone_dev.name}' playback stopped.")

        except Exception as exception_error:
            zone_dev_name = "Unknown Device"
            if zone_dev is not None:
                zone_dev_name = zone_dev.name
            detailed_exception_error = f"Zone Device '{zone_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_volume_decrease(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(f"'process_playback_control_volume_decrease' Roon Controller Action {plugin_action.pluginTypeId} ignored as no Output device specified in Action.")
                return

            if not output_dev.states['output_connected']:
                self.logger.error(f"'process_playback_control_volume_decrease' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev.name}' is disconnected.")
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(f"'process_playback_control_volume_decrease' Roon Controller Action '{plugin_action.pluginTypeId}'"
                                  f" ignored as Output '{output_dev.name}' is not connected to the Roon Core.")
                return

            volume_decrement = -int(plugin_action.props['volumeDecrease'])
            if volume_decrement > -1:
                volume_decrement = -1  # SAFETY CHECK!

            self.globals[ROON][API].change_volume(output_id, volume_decrement, method='relative_step')

        except Exception as exception_error:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            detailed_exception_error = f"Output Device '{output_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_volume_increase(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(f"'process_playback_control_volume_increase' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as no Output device specified in Action.")
                return

            # self.logger.error(f"Roon Controller plugin method 'process_playback_control_next' Plugin Action:\n{plugin_action}\n")

            if not output_dev.states['output_connected']:
                self.logger.error(f"'process_playback_control_volume_increase' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev.name}' is disconnected.")
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(f"'process_playback_control_volume_increase' Roon Controller Action '{plugin_action.pluginTypeId}'"
                                  f" ignored as Output '{output_dev.name}' is not connected to the Roon Core.")
                return

            volume_increment = int(plugin_action.props['volumeIncrease'])
            if volume_increment > 10:
                volume_increment = 1  # SAFETY CHECK!

            self.globals[ROON][API].change_volume(output_id, volume_increment, method='relative_step')

        except Exception as exception_error:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            detailed_exception_error = f"Output Device '{output_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_playback_control_volume_set(self, plugin_action, output_dev):
        try:
            if output_dev is None:
                self.logger.error(f"'process_playback_control_volume_set' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as no Output device specified in Action.")
                return

            if not output_dev.states['output_connected']:
                self.logger.error(f"'process_playback_control_volume_set' Roon Controller Action '{plugin_action.pluginTypeId}' ignored as Output '{output_dev.name}' is disconnected.")
                return

            output_id = output_dev.states['output_id']
            if output_id == '':
                self.logger.error(f"'process_playback_control_volume_set' Roon Controller Action '{plugin_action.pluginTypeId}'"
                                  f" ignored as Output '{output_dev.name}' is not connected to the Roon Core.")
                return

            volume_level = int(plugin_action.props['volumePercentage'])

            self.globals[ROON][API].change_volume(output_id, volume_level, method='absolute')

        except Exception as exception_error:
            output_dev_name = "Unknown Device"
            if output_dev is not None:
                output_dev_name = output_dev.name
            detailed_exception_error = f"Output Device '{output_dev_name}': {exception_error}"
            self.exception_handler(detailed_exception_error, True)  # Log error and display failing statement

    def process_roon_callback_queue(self):
        try:
            self.logger.debug(f"'Roon [SELF] Queue Callback' '{event}': {changed_items}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_roon_callback_state(self, event, changed_items):
        try:
            if event == 'zones_seek_changed':
                self.process_zones_seek_changed(event, changed_items)

            elif event == 'zones_changed':
                self.process_zones_changed(event, changed_items)

            elif event == 'zones_added':
                self.process_zones_added(event, changed_items)

            elif event == 'zones_removed':
                self.process_zones_removed(event, changed_items)

            elif event == 'outputs_changed':
                self.process_outputs_changed(event, changed_items)

            elif event == 'outputs_added':
                self.process_outputs_added(event, changed_items)

            elif event == 'outputs_removed':
                self.process_outputs_removed(event, changed_items)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_roon_volume_control(self, control_key, event, data):
        try:
            self.logger.error(f"'process_roon_volume_control' --> control_key: '{control_key}', event: '{event}' - data: '{data}'")
            # just echo back the new value to set it
            # if event == "set_mute":
            #     roonapi.update_volume_control(control_key, mute=data)
            # elif event == "set_volume":
            #     roonapi.update_volume_control(control_key, volume=data)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zone(self, zone_id, zoneData):
        try:
            self.logger.debug(f"PROCESS ZONE - ZONEDATA:\n{zoneData}\n")

            self.globals[ROON][ZONES][zone_id] = dict()

            self.globals[ROON][ZONES][zone_id][ZONE_ID] = ""
            self.globals[ROON][ZONES][zone_id][QUEUE_ITEMS_REMAINING] = 0
            self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING] = 0
            self.globals[ROON][ZONES][zone_id][DISPLAY_NAME] = ""
            self.globals[ROON][ZONES][zone_id][SETTINGS] = dict()
            self.globals[ROON][ZONES][zone_id][SETTINGS][AUTO_RADIO] = False
            self.globals[ROON][ZONES][zone_id][SETTINGS][SHUFFLE] = False
            self.globals[ROON][ZONES][zone_id][SETTINGS][LOOP] = "disabled"
            self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY] = ""
            self.globals[ROON][ZONES][zone_id][OUTPUTS] = dict()
            self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT] = 0
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING] = dict()
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS] = dict()
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS_COUNT] = 0
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE] = dict()
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE] = dict()
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_1] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_2] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE] = dict()
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3] = ""
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH] = 0
            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION] = 0
            self.globals[ROON][ZONES][zone_id][IS_PREVIOUS_ALLOWED] = False
            self.globals[ROON][ZONES][zone_id][IS_PAUSE_ALLOWED] = False
            self.globals[ROON][ZONES][zone_id][IS_SEEK_ALLOWED] = False
            self.globals[ROON][ZONES][zone_id][STATE] = "stopped"
            self.globals[ROON][ZONES][zone_id][IS_PLAY_ALLOWED] = False
            self.globals[ROON][ZONES][zone_id][IS_NEXT_ALLOWED] = False

            for zoneKey, zoneValue in list(zoneData.items()):

                if zoneKey == 'zone_id':
                    self.globals[ROON][ZONES][zone_id][ZONE_ID] = zoneValue
                if zoneKey == 'queue_items_remaining':
                    self.globals[ROON][ZONES][zone_id][QUEUE_ITEMS_REMAINING] = zoneValue
                elif zoneKey == 'queue_time_remaining':
                    self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING] = zoneValue
                elif zoneKey == 'display_name':
                    self.globals[ROON][ZONES][zone_id][DISPLAY_NAME] = zoneValue
                elif zoneKey == 'settings':
                    self.globals[ROON][ZONES][zone_id][SETTINGS] = dict()
                    for zoneKey2, zoneValue2 in list(zoneValue.items()):
                        if zoneKey2 == 'auto_radio':
                            self.globals[ROON][ZONES][zone_id][SETTINGS][AUTO_RADIO] = bool(zoneValue2)
                        elif zoneKey2 == 'shuffle':
                            self.globals[ROON][ZONES][zone_id][SETTINGS][SHUFFLE] = bool(zoneValue2)
                        elif zoneKey2 == 'loop':
                            self.globals[ROON][ZONES][zone_id][SETTINGS][LOOP] = zoneValue2
                elif zoneKey == 'outputs':
                    self.globals[ROON][ZONES][zone_id][OUTPUTS] = dict()
                    outputCount = 0
                    outputsList = list()

                    for output in zoneValue:


                        outputCount += 1
                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount] = dict()
                        for outputKey, outputData in list(output.items()):
                            if outputKey == 'output_id':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][OUTPUT_ID] = outputData
                                outputsList.append(outputData)
                            elif outputKey == 'display_name':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][DISPLAY_NAME] = outputData
                            elif outputKey == 'zone_id':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][ZONE_ID] = outputData
                            elif outputKey == 'source_controls':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS] = dict()
                                sourceControlsCount = 0
                                for sourceControls in outputData:
                                    sourceControlsCount += 1
                                    self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS][sourceControlsCount] = dict()
                                    for sourceControlKey, sourceControlData in list(sourceControls.items()):
                                        if sourceControlKey == 'status':
                                            self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS][sourceControlsCount][STATUS] = sourceControlData
                                        elif sourceControlKey == 'display_name':
                                            self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS][sourceControlsCount][DISPLAY_NAME] = sourceControlData
                                        elif sourceControlKey == 'control_key':
                                            self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS][sourceControlsCount][CONTROL_KEY] = sourceControlData
                                        elif sourceControlKey == 'supports_standby':
                                            self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS][sourceControlsCount][SUPPORTS_STANDBY] = bool(sourceControlData)
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][SOURCE_CONTROLS_COUNT] = sourceControlsCount
                            elif outputKey == 'volume':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME] = dict()
                                for volumeKey, volumeData in list(outputData.items()):
                                    if volumeKey == 'hard_limit_min':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_HARD_LIMIT_MIN] = volumeData
                                    elif volumeKey == 'min':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_MIN] = volumeData
                                    elif volumeKey == 'is_muted':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_IS_MUTED] = volumeData
                                    elif volumeKey == 'max':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_MAX] = volumeData
                                    elif volumeKey == 'value':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_VALUE] = volumeData
                                    elif volumeKey == 'step':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_STEP] = volumeData
                                    elif volumeKey == 'hard_limit_max':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_HARD_LIMIT_MAX] = volumeData
                                    elif volumeKey == 'soft_limit':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_SOFT_LIMIT] = volumeData
                                    elif volumeKey == 'type':
                                        self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][VOLUME][VOLUME_TYPE] = volumeData

                            elif outputKey == 'can_group_with_output_ids':
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][CAN_GROUP_WITH_OUTPUT_IDS] = dict()
                                canGroupCount = 0
                                for can_group_with_output_id in outputData:
                                    canGroupCount += 1
                                    self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][CAN_GROUP_WITH_OUTPUT_IDS][canGroupCount] = can_group_with_output_id
                                self.globals[ROON][ZONES][zone_id][OUTPUTS][outputCount][CAN_GROUP_WITH_OUTPUT_IDS_COUNT] = canGroupCount
                    self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT] = outputCount
                    outputsList.sort()
                    self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY] = self.convert_output_id_list_to_string(outputsList)

                elif zoneKey == 'now_playing':
                    for zoneKey2, zoneValue2 in list(zoneValue.items()):
                        if zoneKey2 == 'artist_image_keys':
                            artistImageCount = 0
                            for artist_image_key in zoneValue2:
                                artistImageCount += 1
                                self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][artistImageCount] = artist_image_key
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS_COUNT] = artistImageCount
                        elif zoneKey2 == 'image_key':
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY] = zoneValue2
                        elif zoneKey2 == 'one_line':
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE] = dict()
                            for zoneKey3, zoneValue3 in list(zoneValue2.items()):
                                if zoneKey3 == 'line1':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1] = zoneValue3
                        elif zoneKey2 == 'two_line':
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE] = dict()
                            for zoneKey3, zoneValue3 in list(zoneValue2.items()):
                                if zoneKey3 == 'line1':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_1] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_2] = zoneValue3
                        elif zoneKey2 == 'three_line':
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE] = dict()
                            for zoneKey3, zoneValue3 in list(zoneValue2.items()):
                                if zoneKey3 == 'line1':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1] = zoneValue3
                                elif zoneKey3 == 'line2':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2] = zoneValue3
                                elif zoneKey3 == 'line3':
                                    self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3] = zoneValue3
                        if zoneKey2 == 'length':
                            self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH] = zoneValue2
                        if zoneKey2 == 'seek_position':
                            if zoneValue2 is None:
                                self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION] = 0
                            else:
                                self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION] = zoneValue2

                elif zoneKey == 'is_previous_allowed':
                    self.globals[ROON][ZONES][zone_id][IS_PREVIOUS_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_pause_allowed':
                    self.globals[ROON][ZONES][zone_id][IS_PAUSE_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_seek_allowed':
                    self.globals[ROON][ZONES][zone_id][IS_SEEK_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'state':
                    self.globals[ROON][ZONES][zone_id][STATE] = zoneValue
                elif zoneKey == 'is_play_allowed':
                    self.globals[ROON][ZONES][zone_id][IS_PLAY_ALLOWED] = bool(zoneValue)
                elif zoneKey == 'is_next_allowed':
                    self.globals[ROON][ZONES][zone_id][IS_NEXT_ALLOWED] = bool(zoneValue)

            # ### SPECIAL ANNOUCEMENT CODE - START ####
            if self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1] != '':
                zone_state = self.globals[ROON][ZONES][zone_id][STATE]
                self.logger.debug(f"STC. STATE = {zone_state}")

                if zone_state == "playing":
                    announcement_track = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1]
                    work_artist = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2]
                    work_artist = work_artist.replace(' / Various Artists', '')
                    work_artist = work_artist.replace(' / ', ' and ')
                    work_artist = work_artist.replace(' & ', ' and ')
                    work_artist = work_artist.replace(', Jr.', ' junior')
                    announcement_artist = work_artist
                    announcement_album = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3]
                    work_announcement = f"Now playing {announcement_track}"
                    if announcement_artist != '':
                        work_announcement = f"{work_announcement}, by {announcement_artist}"
                    if announcement_album != '':
                        work_announcement = f"{work_announcement}, from the album, {announcement_album}"
                    announcement = work_announcement.replace(' & ', ' and ')
                else:
                    announcement = ""

                self.logger.debug(f"STC. Announcement = {announcement}")

                self.logger.debug(f"STC. OUTPUT ID TO DEV ID = {self.globals[ROON][OUTPUT_ID_TO_DEV_ID]}")

                for key, output in list(self.globals[ROON][ZONES][zone_id][OUTPUTS].items()):
                    self.logger.debug(f"STC. Key = {key}, Output ID = {output}")
                    if 'output_id' in output:
                        roonOutputDevId = self.globals[ROON][OUTPUT_ID_TO_DEV_ID][output[OUTPUT_ID]]
                        self.logger.debug(f"STC. ROONOUTPUTDEVID = {roonOutputDevId}")

                        roonOutputDev = indigo.devices[roonOutputDevId]
                        if roonOutputDev.enabled:
                            nowPlayingVarId = int(roonOutputDev.pluginProps.get('nowPlayingVarId', 0))
                            self.logger.debug(f"STC. INDIGO OUTPUT DEV [{roonOutputDev.name}]: NOWPLAYINGVARID = {nowPlayingVarId}")
                            if nowPlayingVarId != 0:
                                indigo.variable.updateValue(nowPlayingVarId, value=announcement)

            # ### SPECIAL ANNOUCEMENT CODE - END ####

            if self.globals[ROON][ZONES][zone_id][ZONE_ID] != '' and self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY] != '':
                self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_ZONE_ID][self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]] = self.globals[ROON][ZONES][zone_id][ZONE_ID]

                if self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY] not in self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    if self.globals[CONFIG][AUTO_CREATE_DEVICES]:
                        self.auto_create_zone_device(zone_id, self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY])

            else:
                self.logger.error(f"'process_zone' unable to set up 'zoneUniqueIdentityKeyToZoneId'"
                                  f" entry: Zone_id = '{zone_id}', zone_unique_identity_key = '{self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zones(self, zones):
        try:
            for zone_id, zoneData in list(zones.items()):
                self.process_zone(zone_id, zoneData)
                if self.globals[CONFIG][PRINT_ZONE]:
                    self.print_zone(zone_id)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zones_added(self, event, changed_items):
        try:
            # self.print_known_zones_summary('PROCESS ZONES ADDED')

            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals[ROON][API].zone_by_zone_id(zone_id))
                self.process_zone(zone_id, zoneData)
                zoneUniqueIdentityKey = self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]
                self.logger.debug(f"'process_zones_added' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}'. Zone ID = '{zone_id}', "
                                  f"Unique ID = '{zoneUniqueIdentityKey}'\nZoneData:\n{zoneData}\n")

                if zoneUniqueIdentityKey in self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    roonZoneDevId = self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                    self.update_roon_zone_device(roonZoneDevId, zone_id)
                    self.logger.debug(f"'process_zones_added' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}'. Indigo Device = '{indigo.devices[roonZoneDevId].name}', "
                                      f"Zone ID = '{zone_id}', Unique ID = '{zoneUniqueIdentityKey}'")
                else:
                    self.logger.debug(f"'process_zones_added' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}' no matching Indigo device."
                                      f" Zone ID = '{zone_id}', Unique ID = '{zoneUniqueIdentityKey}'")

                    if self.globals[CONFIG][AUTO_CREATE_DEVICES]:
                        self.auto_create_zone_device(zone_id, zoneUniqueIdentityKey)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zones_changed(self, event, changed_items):
        try:
            # self.print_known_zones_summary('PROCESS ZONES CHANGED')

            for zone_id in changed_items:

                zoneData = copy.deepcopy(self.globals[ROON][API].zone_by_zone_id(zone_id))
                self.process_zone(zone_id, zoneData)

                zoneUniqueIdentityKey = self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]
                if zoneUniqueIdentityKey in self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                    roonZoneDevId = self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zoneUniqueIdentityKey]
                    self.update_roon_zone_device(roonZoneDevId, zone_id)
                    self.logger.debug(f"'ZONE CHANGED' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}'."
                                      f" Indigo Device = '{indigo.devices[roonZoneDevId].name}', Unique ID = '{zoneUniqueIdentityKey}'")
                else:
                    self.logger.debug(f"'ZONE CHANGED' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}' no matching Indigo device. Unique ID = '{zoneUniqueIdentityKey}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zones_removed(self, event, changed_items):
        try:
            self.logger.debug("'ZONE REMOVED' INVOKED")
            # self.print_known_zones_summary('PROCESS ZONES REMOVED [START]')

            for zone_id in changed_items:
                zone_display_name = "Unknown Zone"
                zone_unique_identity_key = "None"
                if zone_id in self.globals[ROON][ZONES]:
                    self.logger.debug(f"'process_zones_removed' - Zone:\n{self.globals[ROON][ZONES][zone_id]}")

                    if DISPLAY_NAME in self.globals[ROON][ZONES][zone_id]:
                        zone_display_name = self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]
                    if ZONE_UNIQUE_IDENTITY_KEY in self.globals[ROON][ZONES][zone_id]:
                        zone_unique_identity_key = self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]
                        if zone_unique_identity_key in self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID]:
                            roonZoneDevId = self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][
                                zone_unique_identity_key]
                            self.disconnect_roon_zone_device(roonZoneDevId)
                            self.logger.debug(f"'process_zones_removed' - Zone '{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}'."
                                              f" Indigo Device = '{indigo.devices[roonZoneDevId].name}', Zone ID = '{zone_id}', Unique ID = '{zone_unique_identity_key}'")
                        else:
                            self.logger.debug(f"'process_zones_removed' - Zone '{zone_display_name}' no matching Indigo device. Unique ID = '{zone_unique_identity_key}'")
                    else:
                        self.logger.debug(
                            f"'process_zones_removed' - Zone '{zone_display_name}', Zone ID = '{zone_id}' no matching Indigo device. Unique ID = '{zone_unique_identity_key}'")

                    del self.globals[ROON][ZONES][zone_id]

                    # self.print_known_zones_summary('PROCESS ZONES REMOVED [ZONE REMOVED]')

                else:
                    self.logger.debug(f"'process_zones_removed' - All Zones:\n{self.globals[ROON][ZONES]}")

                self.logger.debug(f"'process_zones_removed' - Zone '{zone_display_name}'. Zone ID =  '{zone_id}', Unique ID = '{zone_unique_identity_key}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_zones_seek_changed(self, event, changed_items):
        zoneData = None
        try:
            for zone_id in changed_items:
                zoneData = copy.deepcopy(self.globals[ROON][API].zone_by_zone_id(zone_id))

                self.globals[ROON][ZONES][zone_id][QUEUE_ITEMS_REMAINING] = zoneData['queue_items_remaining']
                self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING] = zoneData['queue_time_remaining']
                if 'seek_position' in zoneData:
                    self.globals[ROON][ZONES][zone_id][SEEK_POSITION] = zoneData['seek_position']
                    if self.globals[ROON][ZONES][zone_id][SEEK_POSITION] is None:
                        self.globals[ROON][ZONES][zone_id][SEEK_POSITION] = 0
                        self.globals[ROON][ZONES][zone_id][REMAINING] = 0
                    else:
                        if 'now_playing' in zoneData and 'length' in zoneData['now_playing']:
                            self.globals[ROON][ZONES][zone_id][REMAINING] = int(zoneData['now_playing']['length']) - int(self.globals[ROON][ZONES][zone_id][SEEK_POSITION])
                        else:
                            self.globals[ROON][ZONES][zone_id][REMAINING] = 0
                else:
                    self.globals[ROON][ZONES][zone_id][SEEK_POSITION] = 0
                    self.globals[ROON][ZONES][zone_id][REMAINING] = 0

                self.globals[ROON][ZONES][zone_id][STATE] = zoneData.get('state', '-stopped-')

                if ZONE_UNIQUE_IDENTITY_KEY in self.globals[ROON][ZONES][zone_id]:
                    zone_unique_identity_key = self.globals[ROON][ZONES][zone_id][ZONE_UNIQUE_IDENTITY_KEY]
                else:
                    zone_unique_identity_key = "NONE"
                if zone_unique_identity_key in self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID] and zone_unique_identity_key != 'NONE':
                    roonZoneDevId = self.globals[ROON][ZONE_UNIQUE_IDENTITY_KEY_TO_DEV_ID][zone_unique_identity_key]

                    ui_queue_time_remaining = self.ui_time(self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING])
                    ui_seek_position = self.ui_time(self.globals[ROON][ZONES][zone_id][SEEK_POSITION])
                    ui_remaining = self.ui_time(self.globals[ROON][ZONES][zone_id][REMAINING])

                    zone_dev = indigo.devices[roonZoneDevId]
                    key_value_list = [
                        {'key': 'queue_items_remaining', 'value': self.globals[ROON][ZONES][zone_id][QUEUE_ITEMS_REMAINING]},
                        {'key': 'queue_time_remaining', 'value': self.globals[ROON][ZONES][zone_id][QUEUE_TIME_REMAINING]},
                        {'key': 'seek_position', 'value': self.globals[ROON][ZONES][zone_id][SEEK_POSITION]},
                        {'key': 'remaining', 'value': self.globals[ROON][ZONES][zone_id][REMAINING]},
                        {'key': 'state', 'value': self.globals[ROON][ZONES][zone_id][STATE]},
                        {'key': 'ui_queue_time_remaining', 'value': ui_queue_time_remaining},
                        {'key': 'ui_seek_position', 'value': ui_seek_position},
                        {'key': 'ui_remaining', 'value': ui_remaining}
                    ]

                    if zone_dev.states['state'] != self.globals[ROON][ZONES][zone_id][STATE]:
                        key_value_list.append({'key': 'state', 'value': self.globals[ROON][ZONES][zone_id][STATE]})
                        if self.globals[ROON][ZONES][zone_id][STATE] == 'playing':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                        elif self.globals[ROON][ZONES][zone_id][STATE] == 'paused':
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                        else:
                            zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)
                    if zone_dev.states['zone_status'] != self.globals[ROON][ZONES][zone_id][STATE]:
                        key_value_list.append({'key': 'zone_status', 'value': self.globals[ROON][ZONES][zone_id][STATE]})

                    zone_dev.updateStatesOnServer(key_value_list)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def roon_output_id_selected(self, values_dict, type_id, devId):
        try:
            output_id = values_dict.get('roonOutputId', '-')
            if output_id != "-":
                values_dict["roonOutputId"] = values_dict.get("roonOutputId", "**INVALID**")
                values_dict["roonOutputIdUi"] = output_id
            else:
                values_dict["roonOutputIdUi"] = "** INVALID **"

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def roon_zone_unique_identity_key_selected(self, values_dict, type_id, devId):
        try:
            zone_unique_identity_key = values_dict.get('roonZoneUniqueIdentityKey', '-')
            if zone_unique_identity_key != '-':
                values_dict['roonZoneUniqueIdentityKeyUi'] = zone_unique_identity_key
            else:
                values_dict['roonZoneUniqueIdentityKeyUi'] = "** INVALID **"

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def roon_zones_selection(self, values_dict, type_id, zone_dev_id):
        try:
            self.logger.error(f"'roon_zones_selection' values_dict:\n{values_dict}\n")  # TODO: Should this be an error or debug log?

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def supply_available_roon_outputs_list(self, filter, values_dict, type_id, output_dev_id):
        try:
            roonOutputToGroupToName = indigo.devices[output_dev_id].name
            values_dict["roonOutputToGroupTo"] = roonOutputToGroupToName

            available_roon_outputs_devices_list = list()

            for output_dev in indigo.devices:
                if output_dev.deviceTypeId == 'roonOutput' and output_dev.id != output_dev_id and output_dev.states['output_connected']:

                    output_dev_plugin_props = output_dev.pluginProps
                    output_id = output_dev_plugin_props.get('roonOutputId', '')

                    available_roon_outputs_devices_list.append((output_id, output_dev.name))

            def getRoonOutputName(roonOutputNameItem):
                return roonOutputNameItem[1]

            return sorted(available_roon_outputs_devices_list, key=getRoonOutputName)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def ui_time(self, seconds):
        try:
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            if h == 0:
                return "{:d}:{:02d}".format(m, s)  # TODO: Reformat?
            else:
                return "{:d}:{:02d}:{:02d}".format(h, m, s)  # TODO: Reformat?

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def update_roon_output_device(self, roonOutputDevId, output_id):
        output_dev = indigo.devices[roonOutputDevId]

        try:
            auto_name_new_roon_output = bool(output_dev.pluginProps.get('autoNameNewRoonOutput', True))
            if auto_name_new_roon_output and output_dev.name[0:10] == 'new device':

                output_name = f"{self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]}"
                new_device_name = f"Roon Output - {output_name}"

                try:
                    output_dev.pluginProps.update({'roonOutputName': output_name})
                    output_dev.replacePluginPropsOnServer(output_dev.pluginProps)

                    new_device_name = f"Roon Output - {output_name}"

                    self.logger.debug("'update_roon_ouput_device' [Auto-name - New Device];"
                                      f" Debug Info of rename Roon Output from '{output_dev.name}' to '{new_device_name}'")

                    output_dev.name = new_device_name
                    output_dev.replaceOnServer()

                except Exception as exception_error:
                    self.logger.error("'update_roon_output_device' [Auto-name];"  # TODO: Reformat as per output / zone
                                      f" Unable to rename Roon Output from '{output_dev.name}' to '{new_device_name}'. Line '{sys.exc_traceback.tb_lineno}' has error='{exception_error}'")

            if 1 in self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_1 = self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][1]
            else:
                can_group_with_output_id_1 = ""
            if 2 in self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_2 = self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][2]
            else:
                can_group_with_output_id_2 = ""
            if 3 in self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_3 = self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][3]
            else:
                can_group_with_output_id_3 = ""
            if 4 in self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_4 = self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][4]
            else:
                can_group_with_output_id_4 = ""
            if 5 in self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS]:
                can_group_with_output_id_5 = self.globals[ROON][OUTPUTS][output_id][CAN_GROUP_WITH_OUTPUT_IDS][5]
            else:
                can_group_with_output_id_5 = ""

            key_value_list = list()
            if not output_dev.states['output_connected']:
                key_value_list.append({'key': 'output_connected', 'value': True})
            if output_dev.states['output_status'] != 'connected':
                key_value_list.append({'key': 'output_status', 'value': 'connected'})
            if output_dev.states['output_id'] != self.globals[ROON][OUTPUTS][output_id][OUTPUT_ID]:
                key_value_list.append({'key': 'output_id', 'value': self.globals[ROON][OUTPUTS][output_id][OUTPUT_ID]})
            if output_dev.states['display_name'] != self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]:
                if self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME] != '':  # < TEST LEAVING DISPLAY NAME UNALTERED
                    key_value_list.append({'key': 'display_name', 'value': self.globals[ROON][OUTPUTS][output_id][DISPLAY_NAME]})

            if SOURCE_CONTROLS in self.globals[ROON][OUTPUTS][output_id] and self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS_COUNT] > 0:
                if output_dev.states['source_control_1_status'] != self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][STATUS]:
                    key_value_list.append({'key': 'source_control_1_status', 'value': self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][STATUS]})
                if output_dev.states['source_control_1_display_name'] != self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][DISPLAY_NAME]:
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][DISPLAY_NAME]})
                if output_dev.states['source_control_1_control_key'] != self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][CONTROL_KEY]:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][CONTROL_KEY]})
                if output_dev.states['source_control_1_control_key'] != self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][CONTROL_KEY]:
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][CONTROL_KEY]})
                if output_dev.states['source_control_1_supports_standby'] != self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][SUPPORTS_STANDBY]:
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': self.globals[ROON][OUTPUTS][output_id][SOURCE_CONTROLS][1][SUPPORTS_STANDBY]})
            else:
                    key_value_list.append({'key': 'source_control_1_status', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_display_name', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_control_key', 'value': ''})
                    key_value_list.append({'key': 'source_control_1_supports_standby', 'value': False})

            if VOLUME in self.globals[ROON][OUTPUTS][output_id] and len(self.globals[ROON][OUTPUTS][output_id][VOLUME]) > 0:
                if output_dev.states['volume_hard_limit_min'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MIN]:
                    key_value_list.append({'key': 'volume_hard_limit_min', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MIN]})
                if output_dev.states['volume_min'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MIN]:
                    key_value_list.append({'key': 'volume_min', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MIN]})
                if output_dev.states['volume_is_muted'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_IS_MUTED]:
                    key_value_list.append({'key': 'volume_is_muted', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_IS_MUTED]})
                if output_dev.states['volume_max'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MAX]:
                    key_value_list.append({'key': 'volume_max', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_MAX]})
                if output_dev.states['volume_value'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_VALUE]:
                    key_value_list.append({'key': 'volume_value', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_VALUE]})
                if output_dev.states['volume_step'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_STEP]:
                    key_value_list.append({'key': 'volume_step', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_STEP]})
                if output_dev.states['volume_hard_limit_max'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MAX]:
                    key_value_list.append({'key': 'volume_hard_limit_max', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_HARD_LIMIT_MAX]})
                if output_dev.states['volume_soft_limit'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_SOFT_LIMIT]:
                    key_value_list.append({'key': 'volume_soft_limit', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_SOFT_LIMIT]})
                if output_dev.states['volume_type'] != self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_TYPE]:
                    key_value_list.append({'key': 'volume_type', 'value': self.globals[ROON][OUTPUTS][output_id][VOLUME][VOLUME_TYPE]})
            else:
                key_value_list.append({'key': 'volume_hard_limit_min', 'value': 0})
                key_value_list.append({'key': 'volume_min', 'value': 0})
                key_value_list.append({'key': 'volume_is_muted', 'value': False})
                key_value_list.append({'key': 'volume_max', 'value': 0})
                key_value_list.append({'key': 'volume_value', 'value': 0})
                key_value_list.append({'key': 'volume_step', 'value': 0})
                key_value_list.append({'key': 'volume_hard_limit_max', 'value': 0})
                key_value_list.append({'key': 'volume_soft_limit', 'value': 0})
                key_value_list.append({'key': 'volume_type', 'value': 'number'})

            if output_dev.states['can_group_with_output_id_1'] != can_group_with_output_id_1:
                key_value_list.append({'key': 'can_group_with_output_id_1', 'value': can_group_with_output_id_1})
            if output_dev.states['can_group_with_output_id_2'] != can_group_with_output_id_2:
                key_value_list.append({'key': 'can_group_with_output_id_2', 'value': can_group_with_output_id_2})
            if output_dev.states['can_group_with_output_id_3'] != can_group_with_output_id_3:
                key_value_list.append({'key': 'can_group_with_output_id_3', 'value': can_group_with_output_id_3})
            if output_dev.states['can_group_with_output_id_4'] != can_group_with_output_id_4:
                key_value_list.append({'key': 'can_group_with_output_id_4', 'value': can_group_with_output_id_4})
            if output_dev.states['can_group_with_output_id_5'] != can_group_with_output_id_5:
                key_value_list.append({'key': 'can_group_with_output_id_5', 'value': can_group_with_output_id_5})

            if len(key_value_list) > 0:
                output_dev.updateStatesOnServer(key_value_list)
            output_dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOn)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def update_roon_zone_device(self, roonZoneDevId, zone_id):
        new_device_name = ""
        zone_dev = indigo.devices[roonZoneDevId]

        try:
            auto_name_new_roon_zone = bool(zone_dev.pluginProps.get('autoNameNewRoonZone', True))
            if auto_name_new_roon_zone and zone_dev.name[0:10] == 'new device':

                zone_name = f"{self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]}"
                new_device_name = f"Roon Zone - {zone_name}"

                try:
                    zone_dev.pluginProps.update({'roonZoneName': zone_name})
                    zone_dev.replacePluginPropsOnServer(zone_dev.pluginProps)

                    outputCount = self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]
                    if outputCount == 0:
                        new_device_name = f"Roon Zone - {zone_name}"
                    else:
                        temp_zone_name = self.globals[ROON][ZONES][zone_id][OUTPUTS][1][DISPLAY_NAME]
                        for i in range(2, outputCount + 1):
                            temp_zone_name = f"{temp_zone_name} + {self.globals[ROON][ZONES][zone_id][OUTPUTS][i][DISPLAY_NAME]}"
                        new_device_name = f"Roon Zone - {temp_zone_name}"

                    self.logger.debug(f"'update_roon_zone_device' [Auto-name - New Device]; Debug Info of rename Roon Zone from '{zone_dev.name}' to '{new_device_name}'")

                    zone_dev.name = new_device_name
                    zone_dev.replaceOnServer()
                except Exception as exception_error:
                    self.logger.error("'update_roon_zone_device' [Auto-name];"  # TODO: Reformat
                                      f" Unable to rename Roon Zone from '{zone_dev.name}' to '{new_device_name}'. Line '{sys.exc_traceback.tb_lineno}' has error='{exception_error}'")

            # Only check for a roon zone device dynamic rename if a grouped zone
            if self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT] > 1:
                dynamic_rename_check_required = bool(zone_dev.pluginProps.get('dynamicGroupedZoneRename', False))
                if dynamic_rename_check_required:   # True if Dynamic Rename Check Required
                    try:
                        outputCount = self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]
                        if outputCount > 0:
                            new_zone_name = self.globals[ROON][ZONES][zone_id][OUTPUTS][1][DISPLAY_NAME]
                            for i in range(2, outputCount + 1):
                                new_zone_name = f"{new_zone_name} + {self.globals[ROON][ZONES][zone_id][OUTPUTS][i][DISPLAY_NAME]}"
                            new_device_name = f"Roon Zone - {new_zone_name}"

                            old_zone_name = zone_dev.pluginProps.get('roonZoneName', '-')  # e.g. 'Study + Dining Room'

                            if new_device_name != old_zone_name:  # e.g. 'Study + Kitchen' != 'Study + Dining Room'
                                zone_dev_props = zone_dev.pluginProps
                                zone_dev_props['roonZoneName'] = new_zone_name
                                zone_dev.replacePluginPropsOnServer(zone_dev_props)

                            if new_device_name != zone_dev.name:  # e.g. 'Roon Zone - Study + Kitchen'
                                zone_dev.name = new_device_name
                                zone_dev.replaceOnServer()

                    except Exception as exception_error:
                        self.logger.error(f"'update_roon_zone_device' [Dynamic Rename]; Unable to rename Roon Zone from '{originalZoneDevName}' to '{new_device_name}'. "
                                          f"Line '{sys.exc_traceback.tb_lineno}' has error='{exception_error}'")


            if 1 in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                output_id_1 = self.globals[ROON][ZONES][zone_id][OUTPUTS][1][OUTPUT_ID]
            else:
                output_id_1 = ""
            if 2 in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                output_id_2 = self.globals[ROON][ZONES][zone_id][OUTPUTS][2][OUTPUT_ID]
            else:
                output_id_2 = ""
            if 3 in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                output_id_3 = self.globals[ROON][ZONES][zone_id][OUTPUTS][3][OUTPUT_ID]
            else:
                output_id_3 = ""
            if 4 in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                output_id_4 = self.globals[ROON][ZONES][zone_id][OUTPUTS][4][OUTPUT_ID]
            else:
                output_id_4 = ""
            if 5 in self.globals[ROON][ZONES][zone_id][OUTPUTS]:
                output_id_5 = self.globals[ROON][ZONES][zone_id][OUTPUTS][5][OUTPUT_ID]
            else:
                output_id_5 = ""

            if 1 in self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS]:
                artist_image_key_1 = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][1]
            else:
                artist_image_key_1 = ""
            self.process_image(ARTIST, '1', zone_dev, artist_image_key_1)

            if 2 in self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS]:
                artist_image_key_2 = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][2]
            else:
                artist_image_key_2 = ""
            self.process_image(ARTIST, '2', zone_dev, artist_image_key_2)

            if 3 in self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS]:
                artist_image_key_3 = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][3]
            else:
                artist_image_key_3 = ""
            self.process_image(ARTIST, '3', zone_dev, artist_image_key_3)

            if 4 in self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS]:
                artist_image_key_4 = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][4]
            else:
                artist_image_key_4 = ""
            self.process_image(ARTIST, '4', zone_dev, artist_image_key_4)

            if 5 in self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS]:
                artist_image_key_5 = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS][5]
            else:
                artist_image_key_5 = ""
            self.process_image(ARTIST, '5', zone_dev, artist_image_key_5)

            self.process_image(ALBUM, '', zone_dev, self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY])

            zone_status = "stopped"
            if self.globals[ROON][ZONES][zone_id][STATE] == 'playing':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPlaying)
                zone_status = "playing"
            elif self.globals[ROON][ZONES][zone_id][STATE] == 'paused':
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvPaused)
                zone_status = "Paused"
            else:
                zone_dev.updateStateImageOnServer(indigo.kStateImageSel.AvStopped)

            key_value_list = list()

            if not zone_dev.states['zone_connected']:
                key_value_list.append({'key': 'zone_connected', 'value': True})

            if zone_dev.states['zone_status'] != zone_status:
                key_value_list.append({'key': 'zone_status', 'value': zone_status})

            if zone_dev.states['zone_id'] != self.globals[ROON][ZONES][zone_id][ZONE_ID]:
                key_value_list.append({'key': 'zone_id', 'value': self.globals[ROON][ZONES][zone_id][ZONE_ID]})

            if zone_dev.states['display_name'] != self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]:
                key_value_list.append({'key': 'display_name', 'value': self.globals[ROON][ZONES][zone_id][DISPLAY_NAME]})

            if zone_dev.states['auto_radio'] != self.globals[ROON][ZONES][zone_id][SETTINGS][AUTO_RADIO]:
                key_value_list.append({'key': 'auto_radio', 'value': self.globals[ROON][ZONES][zone_id][SETTINGS][AUTO_RADIO]})

            if zone_dev.states['shuffle'] != self.globals[ROON][ZONES][zone_id][SETTINGS][SHUFFLE]:
                key_value_list.append({'key': 'shuffle', 'value': self.globals[ROON][ZONES][zone_id][SETTINGS][SHUFFLE]})

            if zone_dev.states['loop'] != self.globals[ROON][ZONES][zone_id][SETTINGS][LOOP]:
                key_value_list.append({'key': 'loop', 'value': self.globals[ROON][ZONES][zone_id][SETTINGS][LOOP]})

            if zone_dev.states['number_of_outputs'] != self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]:
                key_value_list.append({'key': 'number_of_outputs', 'value': self.globals[ROON][ZONES][zone_id][OUTPUTS_COUNT]})

            if zone_dev.states['output_1_id'] != output_id_1:
                key_value_list.append({'key': 'output_1_id', 'value': output_id_1})

            if zone_dev.states['output_2_id'] != output_id_2:
                key_value_list.append({'key': 'output_2_id', 'value': output_id_2})

            if zone_dev.states['output_3_id'] != output_id_3:
                key_value_list.append({'key': 'output_3_id', 'value': output_id_3})

            if zone_dev.states['output_4_id'] != output_id_4:
                key_value_list.append({'key': 'output_4_id', 'value': output_id_4})

            if zone_dev.states['output_5_id'] != output_id_5:
                key_value_list.append({'key': 'output_5_id', 'value': output_id_5})

            if zone_dev.states['number_of_artist_image_keys'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS_COUNT]:
                key_value_list.append({'key': 'number_of_artist_image_keys', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ARTIST_IMAGE_KEYS_COUNT]})

            if zone_dev.states['artist_image_Key_1_id'] != artist_image_key_1:
                key_value_list.append({'key': 'artist_image_Key_1_id', 'value': artist_image_key_1})

            if zone_dev.states['artist_image_Key_2_id'] != artist_image_key_2:
                key_value_list.append({'key': 'artist_image_Key_2_id', 'value': artist_image_key_2})

            if zone_dev.states['artist_image_Key_3_id'] != artist_image_key_3:
                key_value_list.append({'key': 'artist_image_Key_3_id', 'value': artist_image_key_3})

            if zone_dev.states['artist_image_Key_4_id'] != artist_image_key_4:
                key_value_list.append({'key': 'artist_image_Key_4_id', 'value': artist_image_key_4})

            if zone_dev.states['artist_image_Key_5_id'] != artist_image_key_5:
                key_value_list.append({'key': 'artist_image_Key_5_id', 'value': artist_image_key_5})

            if zone_dev.states['image_key'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY]:
                key_value_list.append({'key': 'image_key', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][IMAGE_KEY]})

            if zone_dev.states['one_line_1'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1]:
                key_value_list.append({'key': 'one_line_1', 'value': f"UNICODE Tëst: {self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1]}"})
                track_title_changed = True
            else:
                track_title_changed = False

            if zone_dev.states['two_line_1'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_1]:
                key_value_list.append({'key': 'two_line_1', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_1]})

            if zone_dev.states['two_line_2'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_2]:
                key_value_list.append({'key': 'two_line_2', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][TWO_LINE][LINE_2]})

            if zone_dev.states['three_line_1'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1]:
                key_value_list.append({'key': 'three_line_1', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_1]})

            if zone_dev.states['three_line_2'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2]:
                key_value_list.append({'key': 'three_line_2', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_2]})

            if zone_dev.states['three_line_3'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3]:
                key_value_list.append({'key': 'three_line_3', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][THREE_LINE][LINE_3]})

            if zone_dev.states['length'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH]:
                key_value_list.append({'key': 'length', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH]})
                ui_length = self.ui_time(self.globals[ROON][ZONES][zone_id][NOW_PLAYING][LENGTH])
                key_value_list.append({'key': 'ui_length', 'value': ui_length})

            if zone_dev.states['seek_position'] != self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION]:
                key_value_list.append({'key': 'seek_position', 'value': self.globals[ROON][ZONES][zone_id][NOW_PLAYING][SEEK_POSITION]})

            if zone_dev.states['remaining'] != 0:
                key_value_list.append({'key': 'remaining', 'value': 0})
                key_value_list.append({'key': 'ui_remaining', 'value': '0:00'})

            if zone_dev.states['is_previous_allowed'] != self.globals[ROON][ZONES][zone_id][IS_PREVIOUS_ALLOWED]:
                key_value_list.append({'key': 'is_previous_allowed', 'value': self.globals[ROON][ZONES][zone_id][IS_PREVIOUS_ALLOWED]})

            if zone_dev.states['is_pause_allowed'] != self.globals[ROON][ZONES][zone_id][IS_PAUSE_ALLOWED]:
                key_value_list.append({'key': 'is_pause_allowed', 'value': self.globals[ROON][ZONES][zone_id][IS_PAUSE_ALLOWED]})

            if zone_dev.states['is_seek_allowed'] != self.globals[ROON][ZONES][zone_id][IS_SEEK_ALLOWED]:
                key_value_list.append({'key': 'is_seek_allowed', 'value': self.globals[ROON][ZONES][zone_id][IS_SEEK_ALLOWED]})

            if zone_dev.states['state'] != self.globals[ROON][ZONES][zone_id][STATE]:
                key_value_list.append({'key': 'state', 'value': self.globals[ROON][ZONES][zone_id][STATE]})

            if zone_dev.states['is_play_allowed'] != self.globals[ROON][ZONES][zone_id][IS_PLAY_ALLOWED]:
                key_value_list.append({'key': 'is_play_allowed', 'value': self.globals[ROON][ZONES][zone_id][IS_PLAY_ALLOWED]})

            if zone_dev.states['is_next_allowed'] != self.globals[ROON][ZONES][zone_id][IS_NEXT_ALLOWED]:
                key_value_list.append({'key': 'is_next_allowed', 'value': self.globals[ROON][ZONES][zone_id][IS_NEXT_ALLOWED]})

            if len(key_value_list) > 0:
                zone_dev.updateStatesOnServer(key_value_list)
                if self.globals[CONFIG][DISPLAY_TRACK_PLAYING] and track_title_changed:
                    zone_dev.description = self.globals[ROON][ZONES][zone_id][NOW_PLAYING][ONE_LINE][LINE_1]
                    zone_dev.replaceOnServer()

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
