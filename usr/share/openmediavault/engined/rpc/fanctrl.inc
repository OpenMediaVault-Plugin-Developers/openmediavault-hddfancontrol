<?php
/**
 * Copyright (C) 2024 Roc R. C.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */

class OMVRpcServiceHddFanCtrl extends \OMV\Rpc\ServiceAbstract
{
    private $hwmon_path = '/sys/class/hwmon/';

    public function getName()
    {
        return "HddFanCtrl";
    }

    public function initialize()
    {
        $this->registerMethod('getFansList');
        $this->registerMethod('toggleFanForHdd');
        $this->registerMethod('getHddList');
        $this->registerMethod('toggleHddCooled');

        $this->registerMethod('getConfig');
        $this->registerMethod('setConfig');

        if (file_exists("/etc/openmediavault/developer-mode"))
        {
            $this->hwmon_path = '/devel/hwmon_dummy/';
        }
    }

    public function getConfig($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        // Get the configuration object.
        $db = \OMV\Config\Database::getInstance();
        $cfg = $db->getAssoc('conf.system.hddfanctrl');
        unset($cfg["drives"]);
        unset($cfg["fans"]);

        return $cfg;
    }

    public function setConfig($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        $db = \OMV\Config\Database::getInstance();
        $cfg = $db->get('conf.system.hddfanctrl');
        $cfg->setAssoc($params);
        $db->set($cfg);

        return $cfg->getAssoc();
    }

    public function getFansList($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        $results = [];

        $db = \OMV\Config\Database::getInstance();
        $fans_cfg = $db->get("conf.system.hddfanctrl.fan");

        foreach (new DirectoryIterator($this->hwmon_path) as $hwmon)
        {
            if(!$hwmon->isDir()) continue;
            if($hwmon->isDot()) continue;

            $fans = new RegexIterator(new DirectoryIterator($hwmon->getPathname()), "/^fan[0-9]+_input/");

            foreach ($fans as $fan)
            {
                if(!$fan->isFile()) continue;
                if($fan->getFilename())
                $hwmon_path = $hwmon->getFilename() . "/" . $fan->getFilename();
                $hwmon_path = preg_replace("/_input$/", "", $hwmon_path);

                $db_fan = NULL;
                foreach($fans_cfg as $_fan_k => $fan_c)
                {
                    if($fan_c->get("hwmon_path") == $hwmon_path)
                    {
                        $db_fan = $fan_c;
                        break;
                    }
                }

                if (is_null($db_fan))
                {
                    $db_fan = new \OMV\Config\ConfigObject("conf.system.hddfanctrl.fan");
                    $db_fan->set("hwmon_path", $hwmon_path);
                    $db_fan->set("hdd_fan", false);
                    $db_fan->setNew();
                    $db->set($db_fan);
                }

                $results[] = [
                    "uuid" => $db_fan->get("uuid"),
                    "hwmon_path" => $hwmon_path,
                    "speed" => file_get_contents($fan->getPathname()),
                    "hdd_fan" => $db_fan->get("hdd_fan")
                ];
            }
        }

        return $this->applyFilter($results, $params['start'], $params['limit'], $params['sortfield'], $params['sortdir']);
    }

    public function toggleFanForHdd($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        $uuid = $params;

        $db = \OMV\Config\Database::getInstance();

        $fans_cfg = $db->get("conf.system.hddfanctrl.fan");
        $fan = NULL;

        foreach($fans_cfg as $_fan_k => $fan_c)
        {
            if($fan_c->get("uuid") == $uuid)
            {
                $fan = $fan_c;
                break;
            }
        }

        assert($fan !== NULL);

        $fan->set("hdd_fan", !$fan->get("hdd_fan"));

        $db->set($fan);

        return $fan->getAssoc();
    }

    public function getHddList($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        $db = \OMV\Config\Database::getInstance();
        $disks_cfg = $db->get("conf.system.hddfanctrl.drive");

        // Get all existing devices except software RAID devices.
		if (FALSE === ($devs = \OMV\System\Storage\StorageDevice::enumerate(OMV_STORAGE_DEVICE_TYPE_DISK))) {
			throw new \OMV\Exception(
			  "Failed to get list of hard disks and hardware RAID devices.");
		}
        $results = [];
        foreach ($devs as $devk => $devv) {
			$sd = \OMV\System\Storage\StorageDevice::getStorageDevice($devv);
			if (is_null($sd) || !$sd->exists())
            {
				continue;
            }
            // Skip devices where no media is available, e.g. CDROM device
            // without an inserted media.
            if (FALSE === $sd->IsMediaAvailable())
            {
                continue;
            }

            $disk_path = $sd->getDeviceFile();
            $disk_sn = NULL;

            // Get all device file symlinks.
			$symlinks = $sd->getDeviceFileSymlinks();
			// Get the 'by-id' device file symlinks.
			$deviceNamesById = [];
			$regex = "/^\/dev\/disk\/by-id\/(.+)$/";
			foreach ($symlinks as $symlinkk => $symlinkv)
            {
                error_log($symlinkv);
				if (1 == preg_match($regex, $symlinkv, $matches))
                {
					$disk_sn= $matches[1];
                    break;
                }
			}
			if (NULL === $disk_sn)
            {
                // No UUID for the device? not sure what that means so we'll skip it for now
                error_log("UUID not found for disk " . $disk_path . ", skipping.");
                continue;
            }

            $db_disk = NULL;
            foreach($disks_cfg as $_disk_k => $disk_c)
            {
                if($disk_c->get("sn") == $disk_sn)
                {
                    $db_disk = $disk_c;
                    break;
                }
            }

            if (is_null($db_disk))
            {
                $db_disk = new \OMV\Config\ConfigObject("conf.system.hddfanctrl.drive");
                $db_disk->set("sn", $disk_sn);
                $db_disk->set("path", $disk_path);
                $db_disk->set("is_cooled", false);
                $db_disk->setNew();
                $db->set($db_disk);
            }

            $results[] = [
                "uuid" => $db_disk->get("uuid"),
                "sn" => $disk_sn,
				"path" => $disk_path,
                "is_cooled" => $db_disk->get("is_cooled")
            ];
        }

        return $results;
    }

    public function toggleHddCooled($params, $context)
    {
        // Validate the RPC caller context.
        $this->validateMethodContext($context, ['role' => OMV_ROLE_ADMINISTRATOR]);

        $uuid = $params;

        $db = \OMV\Config\Database::getInstance();

        $drives_cfg = $db->get("conf.system.hddfanctrl.drive");
        $drive = NULL;

        foreach($drives_cfg as $_drive_k => $drive_c)
        {
            if($drive_c->get("uuid") == $uuid)
            {
                $drive = $drive_c;
                break;
            }
        }

        assert($drive !== NULL);

        $drive->set("is_cooled", !$drive->get("is_cooled"));

        $db->set($drive);

        return $drive->getAssoc();
    }
}
