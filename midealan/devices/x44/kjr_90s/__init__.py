"""The KJR-90S advertises 0x44 and forwards the AC protocol."""

from midealan.const import DeviceType
from midealan.devices.ac import MideaAppliance as KJR90SDevice
from midealan.devices.x44.util import DelegatedModel

MODEL = DelegatedModel(name="KJR-90S", device_type=DeviceType.AC, driver=KJR90SDevice)
