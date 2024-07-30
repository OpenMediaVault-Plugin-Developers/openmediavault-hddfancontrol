# @license   http://www.gnu.org/licenses/gpl.html GPL Version 3
# @author    OpenMediaVault Plugin Developers <plugins@omv-extras.org>
# @author    Roc R.C. <roc@ror3d.xyz>
# @copyright Copyright (c) 2019-2024 OpenMediaVault Plugin Developers
# @copyright Copyright (c) 2024 Roc R.C.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

{% set config = salt['omv_conf.get']('conf.system.hddfanctrl') %}
{% set config_fans = salt['omv_conf.get']('conf.system.hddfanctrl.fan') %}
{% set config_drives = salt['omv_conf.get']('conf.system.hddfanctrl.drive') %}
{% set confDir = '/etc/omv-hddfanctrl' %}

configure_drivetemp_module:
  file.managed:
    - name: "/etc/modules-load.d/omv-hddfanctrl.conf"
    - contents: |
        {{ pillar['headers']['auto_generated'] }}
        {{ pillar['headers']['warning'] }}
        drivetemp
    - mode: 644

restart_systemd_modules_load_service:
  service.running:
    - name: systemd-modules-load
    - enable: True
    - watch:
      - file: configure_drivetemp_module

configure_omv_hddfanctrl_dir:
  file.directory:
    - name: "{{ confDir }}"
    - user: root
    - group: root
    - mode: 755
    - makedirs: True

configure_omv_hddfanctrl_config:
  file.managed:
    - name: "{{ confDir }}/fanctrl.conf"
    - user: root
    - group: root
    - mode: 644
    - contents: |
        {{ pillar['headers']['auto_generated'] }}
        {{ pillar['headers']['warning'] }}
        fan_pwm_file={% for fan in config_fans %}{% if fan.hdd_fan %} /sys/class/hwmon/{{ fan.hwmon_path | regex_replace('fan([0-9]+)$', 'pwm\\1') }}{% endif %}{% endfor %}
        fan_min_pct={{ config.min_speed_pct }}
        min_temp={{ config.temp_min }}
        max_temp={{ config.temp_max }}
        temp_update_interval={{ config.temp_update_interval_seconds }}
        spindown_time={{ config.spindown_minutes }}
        drive_temp_file={% for drive in config_drives %}{% if drive.is_cooled %} /dev/disk/by-id/{{ drive.sn }}{% endif %}{% endfor %}

{% if config.enabled | to_bool %}

start_omv_hddfanctrl_service:
  service.running:
    - name: omv-hddfanctrl
    - enable: True
    - watch:
      - file: configure_omv_hddfanctrl_config

{% else %}

stop_omv_hddfanctrl_service:
  service.dead:
    - name: omv-hddfanctrl
    - enable: False

{% endif %}
