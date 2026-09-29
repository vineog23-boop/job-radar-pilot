from __future__ import annotations

from types import SimpleNamespace

from scrapling.parser import Adaptor

from job_radar.models import SourceConfig, SourceKind
from job_radar.sources.gupy import GupyAdapter


def test_gupy_extracts_current_rendered_job_card() -> None:
    url = "https://portal.gupy.io/job-search/term%3Ddesenvolvedor%20junior"
    html = """
    <a href="https://acme.gupy.io/job/TOKEN-123?jobBoardSource=gupy_portal">
      <div class="MuiCard-root MuiCard-job_default">
        <p class="MuiTypography-body-medium">Acme Tecnologia</p>
        <h3>Pessoa Desenvolvedora Java Júnior</h3>
        <span data-testid="job-location">São Paulo - SP</span>
      </div>
    </a>
    """
    adaptor = Adaptor(html, url=url)
    page = SimpleNamespace(
        status=200,
        text=html,
        url=url,
        css=adaptor.css,
        urljoin=adaptor.urljoin,
    )
    config = SourceConfig(
        code="gupy",
        kind=SourceKind.GUPY,
        start_url=url,
        enabled=True,
        max_pages=1,
        min_interval_seconds=1,
        requires_auth=False,
    )

    parsed = GupyAdapter().parse_page(page, config)

    assert parsed.cards_observed == 1
    assert len(parsed.records) == 1
    record = parsed.records[0]
    assert record.title == "Pessoa Desenvolvedora Java Júnior"
    assert record.company == "Acme Tecnologia"
    assert record.location == "São Paulo - SP"
    assert record.canonical_url == "https://acme.gupy.io/job/TOKEN-123"
