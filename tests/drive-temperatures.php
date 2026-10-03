<?php
/** Run: php -d zend.assertions=-1 tests/drive-temperatures.php */
namespace OMV\System\Storage {
    class StorageDevice {
        public static $devices = [];
        public static function enumerate($type) { return array_keys(self::$devices); }
        public static function getStorageDevice($path) { return self::$devices[$path]; }
    }
}

namespace {
    // Reuse the minimal OMV stubs and exercise the selection regression too.
    require __DIR__ . '/toggle-selection.php';
    define('OMV_STORAGE_DEVICE_TYPE_DISK', 1);

    class TemperatureProbe {
        public $noCheck;
        public $cached;
        public $value;
        public $fail;
        public $reads = 0;
        public function __construct($cached, $value, $fail = false) {
            $this->cached = $cached;
            $this->value = $value;
            $this->fail = $fail;
        }
        public function setNoCheck($value) { $this->noCheck = $value; }
        public function getPowerMode() {
            check($this->noCheck === 'standby', 'Probe must respect disk standby');
            if ($this->fail) { throw new \OMV\Exception('Temperature probe failed'); }
            return $this->cached ? 'ACTIVE or IDLE' : 'STANDBY';
        }
        public function isCached() { return $this->cached; }
        public function getTemperature() {
            check($this->cached, 'Standby temperature must not be queried');
            ++$this->reads;
            return $this->value;
        }
    }

    class TemperatureDevice {
        public $path;
        public $serial;
        public $supported;
        public $probe;
        public function __construct($path, $serial, $supported, $probe) {
            $this->path = $path;
            $this->serial = $serial;
            $this->supported = $supported;
            $this->probe = $probe;
        }
        public function exists() { return true; }
        public function IsMediaAvailable() { return true; }
        public function getDeviceFile() { return $this->path; }
        public function getDeviceFileSymlinks() { return ['/dev/disk/by-id/' . $this->serial]; }
        public function hasSmartSupport() { return $this->supported; }
        public function getSmartInformation() {
            check($this->supported, 'Unsupported devices must not be probed');
            return $this->probe;
        }
    }

    $cases = [
        ['awake', true, true, 36, false, 36],
        ['zero', true, true, 0, false, 0],
        ['standby', true, false, 99, false, ''],
        ['unsupported', false, false, 99, false, ''],
        ['no-sensor', true, true, false, false, ''],
        ['failed-probe', true, true, 99, true, '']
    ];
    $db->objects['conf.system.hddfanctrl.drive'] = [];
    foreach ($cases as $index => [$name, $supported, $cached, $value, $fail, $expected]) {
        $path = '/dev/test' . $index;
        $serial = 'temperature-' . $name;
        $probe = new TemperatureProbe($cached, $value, $fail);
        $device = new TemperatureDevice($path, $serial, $supported, $probe);
        \OMV\System\Storage\StorageDevice::$devices[$path] = $device;
        $db->objects['conf.system.hddfanctrl.drive'][] = new \OMV\Config\ConfigObject([
            'uuid' => 'temperature-test-' . $index,
            'sn' => $serial,
            'is_cooled' => $index === 0
        ]);
    }
    $writes = $db->writes;
    $result = $service->getHddList([], $context);
    check(count($result) === count($cases), 'Unavailable temperatures must not hide disks');
    foreach ($cases as $index => [$name, $supported, $cached, $value, $fail, $expected]) {
        check($result[$index]['temperature'] === $expected, 'Unexpected temperature for ' . $name);
        check($result[$index]['is_cooled'] === ($index === 0), 'Cooled selection changed');
        $probe = \OMV\System\Storage\StorageDevice::$devices['/dev/test' . $index]->probe;
        check($probe->reads === (($supported && $cached && !$fail) ? 1 : 0), 'Unexpected probe for ' . $name);
    }
    check($db->writes === $writes, 'Listing temperatures must not modify existing selections');
    echo "Drive temperatures, standby, unavailable probes and unchanged selections: OK\n";
}
