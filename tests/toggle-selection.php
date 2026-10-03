<?php
/**
 * Standalone regression checks for selection RPCs; no OMV installation needed.
 * Run: php -d zend.assertions=-1 tests/toggle-selection.php
 */
namespace OMV {
    class Exception extends \Exception {}
}

namespace OMV\Rpc {
    abstract class ServiceAbstract {
        protected function validateMethodContext($context, $requirements) {
            if (($context['role'] ?? NULL) !== $requirements['role']) {
                throw new \OMV\Exception('Administrator required');
            }
        }
    }
}

namespace OMV\Config {
    class ConfigObject {
        private $values;
        public function __construct($values) { $this->values = $values; }
        public function get($name) { return $this->values[$name]; }
        public function set($name, $value) { $this->values[$name] = $value; }
        public function getAssoc() { return $this->values; }
    }

    class Database {
        public static $instance;
        public $objects = [];
        public $writes = 0;
        public static function getInstance() { return self::$instance; }
        public function get($name) { return $this->objects[$name]; }
        public function set($object) { ++$this->writes; }
    }
}

namespace {
    define('OMV_ROLE_ADMINISTRATOR', 'admin');
    require $argv[1] ?? __DIR__ . '/../usr/share/openmediavault/engined/rpc/fanctrl.inc';

    function check($condition, $message) {
        if (!$condition) {
            throw new \RuntimeException($message);
        }
    }

    $db = new \OMV\Config\Database();
    \OMV\Config\Database::$instance = $db;
    $service = new \OMVRpcServiceHddFanCtrl();
    $context = ['role' => OMV_ROLE_ADMINISTRATOR];
    $uuid = '11111111-1111-4111-8111-111111111111';
    $otherUuid = '22222222-2222-4222-8222-222222222222';
    $unknownUuid = '33333333-3333-4333-8333-333333333333';

    foreach ([
        ['toggleFanForHdd', 'conf.system.hddfanctrl.fan', 'hdd_fan', 'fan'],
        ['toggleHddCooled', 'conf.system.hddfanctrl.drive', 'is_cooled', 'drive']
    ] as [$method, $collection, $field, $kind]) {
        $other = new \OMV\Config\ConfigObject(['uuid' => $otherUuid, $field => false]);
        $selected = new \OMV\Config\ConfigObject(['uuid' => $uuid, $field => false]);
        $db->objects[$collection] = [$other, $selected];

        foreach ([NULL, false, 42, '', [], ['uuid' => NULL], ['uuid' => []], ['uuid' => 42]] as $params) {
            $writes = $db->writes;
            try {
                $service->$method($params, $context);
                throw new \RuntimeException("$method accepted an invalid selection");
            } catch (\OMV\Exception $exception) {
                check($exception->getMessage() === "No $kind selected. Select a $kind from the list.",
                    "$method did not return the expected selection error");
            }
            check($db->writes === $writes && !$selected->get($field) && !$other->get($field),
                "$method modified configuration for invalid parameters");
        }

        foreach ([$unknownUuid, ['uuid' => $unknownUuid]] as $params) {
            $writes = $db->writes;
            try {
                $service->$method($params, $context);
                throw new \RuntimeException("$method accepted a stale selection");
            } catch (\OMV\Exception $exception) {
                check(strpos($exception->getMessage(), 'was not found') !== false,
                    "$method did not report the stale selection");
            }
            check($db->writes === $writes, "$method saved a stale selection");
        }

        // Both the workbench object and legacy scalar UUID remain supported.
        foreach ([['uuid' => $uuid], $uuid] as $params) {
            foreach ([true, false] as $expected) {
                $writes = $db->writes;
                $result = $service->$method($params, $context);
                check($result['uuid'] === $uuid && $result[$field] === $expected,
                    "$method did not toggle the selected object");
                check($db->writes === $writes + 1 && !$other->get($field),
                    "$method did not preserve the other object");
            }
        }

        $writes = $db->writes;
        try {
            $service->$method(['uuid' => $uuid], ['role' => 'user']);
            throw new \RuntimeException("$method accepted a non-administrator");
        } catch (\OMV\Exception $exception) {
            check($exception->getMessage() === 'Administrator required', 'Context validation was bypassed');
        }
        check($db->writes === $writes && !$selected->get($field), 'Unauthorized call changed configuration');
        echo "$method: OK\n";
    }
}
