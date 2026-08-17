from types import SimpleNamespace

from app.models.task import TaskStatus
from features.bittorrent_pack.cards import BT_PEERS_FIELD, BTTaskCard
from features.ed2k_pack.cards import ED2K_PEERS_FIELD, ED2kTaskCard


def test_ed2k_task_card_displays_active_and_total_peers():
    task = SimpleNamespace(activePeerCount=2, totalPeerCount=10)

    assert ED2K_PEERS_FIELD in ED2kTaskCard.infoFields
    assert ED2K_PEERS_FIELD.icon.value == "Info"
    assert ED2K_PEERS_FIELD.formats[TaskStatus.RUNNING](task, 0, 0) == "2/10 Peers"


def test_ed2k_peer_field_hides_for_an_older_daemon():
    task = SimpleNamespace(activePeerCount=None, totalPeerCount=10)

    assert ED2K_PEERS_FIELD.formats[TaskStatus.RUNNING](task, 0, 0) is None


def test_bt_task_card_displays_connected_and_known_peers():
    task = SimpleNamespace(peerCount=3, totalPeerCount=17)

    assert BT_PEERS_FIELD in BTTaskCard.infoFields
    assert BT_PEERS_FIELD.icon.value == "Info"
    assert BT_PEERS_FIELD.formats[TaskStatus.RUNNING](task, 0, 0) == "3/17 Peers"
