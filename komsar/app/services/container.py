from types import SimpleNamespace

from ..blockchain.chain import Blockchain
from ..repository import SqlRepository
from .asset_service import AssetService
from .decryption_service import DecryptionCenter
from .result_cache import ResultCache
from .messaging_service import MessagingService


def build_services(app) -> SimpleNamespace:
    repo = SqlRepository()
    chain = Blockchain()
    assets = AssetService(repo, chain)
    return SimpleNamespace(
        repo=repo, chain=chain, assets=assets, cache=ResultCache(),
        messaging=MessagingService.from_app(app, repo, assets),
        decryption=DecryptionCenter(repo, app.config["DB_MASTER_KEY"], assets),
    )
