"""IaC parity for the Event Hubs private networking option (static checks, no Azure calls)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EVENT_HUB_LABS = ["disaster-signal-fusion", "wind-turbine-continual-learning"]


@pytest.mark.parametrize("lab", EVENT_HUB_LABS)
def test_event_hubs_public_access_follows_private_networking_in_both_tools(lab):
    infra = ROOT / "labs" / lab / "infra"
    bicep, tf = (infra / "main.bicep").read_text(), (infra / "terraform/main.tf").read_text()
    variables = (infra / "terraform/variables.tf").read_text()
    # public stays the cheap default in both tools
    assert "param privateNetworking bool = false" in bicep
    assert re.search(r'variable "private_networking" \{.*?default\s+= false', variables, re.S)
    assert "publicNetworkAccess: privateNetworking ? 'Disabled' : 'Enabled'" in bicep
    assert "public_network_access_enabled = !var.private_networking" in tf
    # a private endpoint on the namespace, the servicebus private DNS zone and an NSG, in both
    assert "groupIds: ['namespace']" in bicep and "privatelink.servicebus.windows.net" in bicep
    assert "networkSecurityGroup: { id: nsg.id }" in bicep
    assert 'eventhubs = "privatelink.servicebus.windows.net"' in tf
    module = ROOT / "infra/terraform/modules"
    assert 'subresource_names              = ["namespace"]' in (module / "eventhubs/main.tf").read_text()
    net = (module / "private-network/main.tf").read_text()
    assert "azurerm_subnet_network_security_group_association" in net


def test_event_hubs_module_is_no_longer_hard_coded_public():
    main = (ROOT / "infra/terraform/modules/eventhubs/main.tf").read_text()
    assert "public_network_access_enabled = true" not in main
    assert "public_network_access_enabled = var.public_network_access_enabled" in main
