"""Bound stalled archive requests without limiting active large downloads."""
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class MastTimeoutAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            # Read timeout measures inactivity, not the whole FITS transfer.
            kwargs["timeout"] = (15, 60)
        return super().send(request, **kwargs)


def configure_mast_network(observations):
    # Astroquery shares this session with its discovery portal client.
    # MAST's POST endpoints here only query archive metadata.
    retry = Retry(total=2, connect=2, read=2, status=0,
                  allowed_methods=frozenset(("GET", "HEAD", "POST")),
                  backoff_factor=0.5)
    observations._session.mount("https://mast.stsci.edu/",
                                MastTimeoutAdapter(max_retries=retry))
