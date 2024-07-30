#!/usr/bin/env dash
#
# This file is part of OpenMediaVault.
#
# @license   http://www.gnu.org/licenses/gpl.html GPL Version 3
# @author    Volker Theile <volker.theile@openmediavault.org>
# @author    Roc R. C. <roc@ror3d.xyz>
# @copyright Copyright (c) 2009-2024 Volker Theile
# @copyright Copyright (c) 2024 Roc R. C.
#
# OpenMediaVault is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.
#
# OpenMediaVault is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with OpenMediaVault. If not, see <http://www.gnu.org/licenses/>.

set -e

if ! omv-confdbadm exists "conf.system.hddfanctrl"; then
	omv-confdbadm read --defaults "conf.system.hddfanctrl" | omv-confdbadm update "conf.system.hddfanctrl" -
fi

exit 0
