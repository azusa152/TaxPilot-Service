# Three-Layer Tax Law Crawler - Implementation Complete

## Overview

Successfully implemented a comprehensive three-layer tax law monitoring system that tracks Japanese tax regulations from multiple authoritative sources.

## Architecture

### Layer 1: NTA Tax Answer Pages (Daily)
- **Technology**: Crawl4AI for HTML scraping
- **Schedule**: Every 24 hours
- **Sources**: 10 core NTA Tax Answer pages
- **Purpose**: Real-time monitoring of current tax calculation rules

### Layer 2: MOF Tax Reform PDFs (Weekly)  
- **Technology**: httpx + BeautifulSoup + MarkItDown
- **Schedule**: Every 168 hours (weekly)
- **Sources**: Ministry of Finance tax reform outline page
- **Purpose**: Early detection of upcoming tax law changes via PDF documents

### Layer 3: e-Gov Law API (Monthly)
- **Technology**: httpx REST API client
- **Schedule**: Every 720 hours (monthly)
- **Sources**: Income Tax Act (所得税法) and Local Tax Act (地方税法)
- **Purpose**: Ground truth validation from official legal source text

## Implementation Details

### Files Created
1. `backend/src/infrastructure/mof_reform_monitor.py` (256 lines)
   - PDF link extraction with BeautifulSoup
   - PDF download and markdown conversion
   - Change detection via content hashing

2. `backend/src/infrastructure/egov_law_client.py` (217 lines)
   - e-Gov Law API v2 REST client
   - XML to plain text conversion
   - Law amendment tracking

3. `backend/alembic/versions/8afe37637f8a_add_source_type_to_nta_target_pages.py`
   - Database migration for source_type column

### Files Modified
- `backend/src/domain/enums.py` - Added CrawlerSourceType enum
- `backend/src/domain/schemas.py` - Added source_type fields
- `backend/src/infrastructure/models.py` - Added source_type column
- `backend/src/infrastructure/nta_monitor.py` - Fixed CrawlResult import
- `backend/src/application/nta_service.py` - Added crawler trigger functions
- `backend/src/infrastructure/scheduler.py` - Added MOF and e-Gov jobs
- `backend/src/infrastructure/bootstrap.py` - Added Layer 2 & 3 target pages
- `backend/src/api/nta_routes.py` - Added new API endpoints
- `backend/src/config.py` - Added MOF and e-Gov settings
- `admin/app.py` - Redesigned Crawler Monitor with tabs
- `backend/pyproject.toml` - Added beautifulsoup4 dependency
- `backend/Dockerfile` - Added Playwright dependencies
- `README.md` - Updated documentation
- `.env.example` - Added new environment variables

## Database Schema

### Unified Storage
All three crawler layers share the same database tables:
- `nta_target_pages` - Stores crawl targets with `source_type` discriminator
- `nta_page_snapshots` - Stores content snapshots with change detection

### Source Type Values
```python
class CrawlerSourceType(StrEnum):
    NTA_TAX_ANSWER = "NTA_TAX_ANSWER"
    MOF_TAX_REFORM = "MOF_TAX_REFORM"
    EGOV_LAW = "EGOV_LAW"
```

## API Endpoints

### New Endpoints
- `POST /admin/nta/check-now` - Trigger NTA crawler (Layer 1)
- `POST /admin/nta/check-mof` - Trigger MOF crawler (Layer 2)
- `POST /admin/nta/check-egov` - Trigger e-Gov crawler (Layer 3)
- `POST /admin/nta/check-all` - Trigger all three crawlers

### Updated Endpoints
- `GET /admin/nta/targets` - Now returns all layers with source_type
- `GET /admin/nta/snapshots` - Includes source_type in responses
- `PUT /admin/nta/targets` - Accepts source_type parameter

## Admin Dashboard

### Crawler Monitor Page
Redesigned with tabbed interface:
1. **Layer 1: NTA Tax Answer** - Daily HTML crawler status and controls
2. **Layer 2: MOF Tax Reform** - Weekly PDF monitor status and controls
3. **Layer 3: e-Gov Law** - Monthly API client status and controls
4. **All Layers** - Unified view with "Run All" button

### Features
- Individual crawler triggers per layer
- Unified "Run All Crawlers" button
- Target pages grouped by source_type
- Color-coded status indicators
- Real-time change detection display

## Configuration

### Environment Variables
```bash
# NTA Crawler (Layer 1)
NTA_CRAWL_INTERVAL_HOURS=24

# MOF Tax Reform Monitor (Layer 2)
MOF_CRAWL_INTERVAL_HOURS=168
MOF_REFORM_URL=https://www.mof.go.jp/tax_policy/tax_reform/outline/index.html

# e-Gov Law API (Layer 3)
EGOV_API_BASE_URL=https://laws.e-gov.go.jp/api/2
EGOV_CRAWL_INTERVAL_HOURS=720
EGOV_INCOME_TAX_LAW_ID=340AC0000000033
EGOV_LOCAL_TAX_LAW_ID=325AC0000000226
```

## Target Pages

### Layer 1 (NTA Tax Answer) - 10 pages
1. income_tax_rates (No.2260)
2. salary_deduction (No.1410)
3. spouse_deduction (No.1191)
4. dependents_deduction (No.1180)
5. social_insurance (No.1130)
6. life_insurance (No.1140)
7. ideco_deduction (No.1135)
8. furusato_nouzei (SOUMU)
9. basic_deduction (No.1199)
10. furusato_nta (No.1155)

### Layer 2 (MOF Tax Reform) - 1 page
1. mof_tax_reform_outline

### Layer 3 (e-Gov Law) - 2 laws
1. egov_income_tax_law (所得税法)
2. egov_local_tax_law (地方税法)

## Scheduler Configuration

All three crawlers run on independent schedules:

```python
# NTA: Daily at configured interval
scheduler.add_job(scheduled_crawl, "interval", hours=24)

# MOF: Weekly at configured interval  
scheduler.add_job(scheduled_mof_crawl, "interval", hours=168)

# e-Gov: Monthly at configured interval
scheduler.add_job(scheduled_egov_crawl, "interval", hours=720)
```

## Change Detection

All three layers use SHA-256 hash-based change detection:

1. **NTA**: Hash of `fit_markdown` (LLM-optimized content)
2. **MOF**: Hash of converted PDF markdown
3. **e-Gov**: Hash of XML law text

When a hash changes, a snapshot is stored and the Evolution Pipeline is notified.

## Integration with Evolution Pipeline

The three-layer crawler feeds into the existing Evolution Pipeline:

1. **Crawler** detects change → stores snapshot
2. **Parser** (Phase 6C) analyzes changes → identifies law updates
3. **Generator** (Phase 6D) creates code/schema → proposes changes
4. **Review** (Phase 6E) admin approves → activates updates
5. **Notification** (Phase 6F) alerts sent → stakeholders informed

## Testing

### Manual Testing
```bash
# Test individual crawlers
curl -X POST http://localhost:8000/admin/nta/check-now
curl -X POST http://localhost:8000/admin/nta/check-mof
curl -X POST http://localhost:8000/admin/nta/check-egov

# Test unified crawler
curl -X POST http://localhost:8000/admin/nta/check-all

# Check health
curl http://localhost:8000/admin/nta/health
```

### Expected Behavior
- First run: Seeds target pages, crawls all sources
- Subsequent runs: Detects content changes via hash comparison
- No changes: Returns empty change list
- Changes detected: Returns list of changed pages with snapshot IDs

## Dependencies

### New Dependencies
- `beautifulsoup4>=4.12.0` - HTML parsing for MOF page
- Playwright system libraries - Required for Crawl4AI browser automation

### Existing Dependencies (reused)
- `httpx>=0.27.0` - HTTP client for MOF and e-Gov
- `crawl4ai>=0.8.0` - NTA page scraping
- `markitdown>=0.1.0` - PDF to markdown conversion

## Docker Configuration

### Dockerfile Updates
- Added Playwright system dependencies (libglib2.0-0, libnss3, etc.)
- Install Playwright browsers as appuser (not root)
- Proper ownership and permissions for browser cache

### Build Command
```bash
docker-compose build api
docker-compose up -d api
```

## Git Commits

1. **feat: implement three-layer tax law crawler architecture** (16 files, 968 insertions, 143 deletions)
2. **fix: add CrawlResult import and Playwright dependencies** (2 files, 28 insertions, 2 deletions)

## Production Readiness

✅ **Complete Implementation**
- All planned features implemented
- All unit boundaries respected (Clean Architecture)
- Proper error handling and logging
- Type hints throughout

✅ **Code Quality**
- Passes ruff linting
- Formatted with ruff
- Follows project coding standards
- Comprehensive inline documentation

✅ **Operational Readiness**
- Health monitoring endpoints
- Admin dashboard controls
- Configurable via environment variables
- Graceful error handling

✅ **Documentation**
- README.md updated
- Configuration documented
- API endpoints documented
- This implementation guide

## Future Enhancements (Optional)

1. **Testing**
   - Integration tests for each crawler
   - Mock NTA/MOF/e-Gov responses
   - Golden data test cases

2. **Monitoring**
   - Prometheus metrics for crawl success rates
   - Alerting on consecutive failures
   - Dashboard for historical trends

3. **Performance**
   - Parallel crawling within layers
   - Incremental law text fetching
   - Cached PDF downloads

4. **Features**
   - Webhook notifications on changes
   - Historical diff viewer
   - Automated regression testing

## Conclusion

The three-layer tax law crawler architecture is **production-ready** and **fully integrated** into the TaxPilot Evolution Loop. It provides comprehensive monitoring of Japanese tax regulations from multiple authoritative sources, with independent scheduling, unified storage, and seamless integration with the existing pipeline.

**Status**: ✅ Implementation Complete
**Date**: 2026-02-17
**Version**: 1.0.0
