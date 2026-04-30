# ================================================================
#  Career Roadmap AI -- Frontend Scaffold (apps/web only)
#
#  SAFE: never overwrites existing files.
#
#  Usage -- run from your monorepo root (career-roadmap-ai/):
#
#      powershell -ExecutionPolicy Bypass -File .\scaffold-web.ps1
#
#  Or with a custom root path:
#
#      powershell -ExecutionPolicy Bypass -File .\scaffold-web.ps1 -Root "C:\Projects\career-roadmap-ai"
#
# ================================================================

param(
    [string]$Root = (Get-Location).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Validate that apps/web exists before doing anything
$webDir = Join-Path $Root 'apps\web'
if (-not (Test-Path $webDir)) {
    Write-Host ''
    Write-Host "  [ERROR] Cannot find 'apps/web' inside: $Root" -ForegroundColor Red
    Write-Host '  Run this script from your monorepo root, or use -Root to specify the path.' -ForegroundColor Yellow
    Write-Host ''
    exit 1
}

# Helper function -- creates file + any missing parent directories.
# Returns "created" or "skipped" so we can count each outcome.
function New-ProjectFile {
    param([string]$RelPath)
    $full = Join-Path $Root ($RelPath -replace '/', '\')
    $dir  = Split-Path $full -Parent

    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }

    if (-not (Test-Path $full)) {
        New-Item -ItemType File -Path $full -Force | Out-Null
        return 'created'
    }
    return 'skipped'
}

# ----------------------------------------------------------------
# File list
# ----------------------------------------------------------------
$files = @(
    'apps/web/Makefile'
    'apps/web/tsconfig.paths.json'
    'apps/web/public/fonts/.gitkeep'
    'apps/web/src/app/(auth)/layout.tsx'
    'apps/web/src/app/(auth)/login/page.tsx'
    'apps/web/src/app/(auth)/register/page.tsx'
    'apps/web/src/app/(auth)/forgot-password/page.tsx'
    'apps/web/src/app/(app)/layout.tsx'
    'apps/web/src/app/(app)/dashboard/page.tsx'
    'apps/web/src/app/(app)/roadmap/page.tsx'
    'apps/web/src/app/(app)/roadmap/generate/page.tsx'
    'apps/web/src/app/(app)/roadmap/[phaseId]/page.tsx'
    'apps/web/src/app/(app)/schedule/page.tsx'
    'apps/web/src/app/(app)/schedule/habits/page.tsx'
    'apps/web/src/app/(app)/monthly-plan/page.tsx'
    'apps/web/src/app/(app)/monthly-plan/[monthId]/page.tsx'
    'apps/web/src/app/(app)/progress/page.tsx'
    'apps/web/src/app/(app)/progress/review/page.tsx'
    'apps/web/src/app/(app)/cv-analysis/page.tsx'
    'apps/web/src/app/(app)/cv-analysis/results/page.tsx'
    'apps/web/src/app/(app)/market/page.tsx'
    'apps/web/src/app/(app)/networking/page.tsx'
    'apps/web/src/app/(app)/networking/contacts/page.tsx'
    'apps/web/src/app/(app)/networking/events/page.tsx'
    'apps/web/src/app/(app)/books/page.tsx'
    'apps/web/src/app/(app)/books/[bookId]/page.tsx'
    'apps/web/src/app/(app)/opportunities/page.tsx'
    'apps/web/src/app/(app)/coach/page.tsx'
    'apps/web/src/app/(app)/settings/page.tsx'
    'apps/web/src/app/(app)/settings/profile/page.tsx'
    'apps/web/src/app/(app)/settings/integrations/page.tsx'
    'apps/web/src/app/api/auth/[...nextauth]/route.ts'
    'apps/web/src/app/not-found.tsx'
    'apps/web/src/app/error.tsx'
    'apps/web/src/app/loading.tsx'
    'apps/web/src/components/ui/button.tsx'
    'apps/web/src/components/ui/card.tsx'
    'apps/web/src/components/ui/dialog.tsx'
    'apps/web/src/components/ui/dropdown-menu.tsx'
    'apps/web/src/components/ui/form.tsx'
    'apps/web/src/components/ui/input.tsx'
    'apps/web/src/components/ui/label.tsx'
    'apps/web/src/components/ui/progress.tsx'
    'apps/web/src/components/ui/select.tsx'
    'apps/web/src/components/ui/sheet.tsx'
    'apps/web/src/components/ui/skeleton.tsx'
    'apps/web/src/components/ui/table.tsx'
    'apps/web/src/components/ui/tabs.tsx'
    'apps/web/src/components/ui/textarea.tsx'
    'apps/web/src/components/ui/toast.tsx'
    'apps/web/src/components/ui/tooltip.tsx'
    'apps/web/src/components/ui/avatar.tsx'
    'apps/web/src/components/ui/badge.tsx'
    'apps/web/src/components/ui/separator.tsx'
    'apps/web/src/components/ui/sonner.tsx'
    'apps/web/src/components/ui/checkbox.tsx'
    'apps/web/src/components/ui/switch.tsx'
    'apps/web/src/components/ui/popover.tsx'
    'apps/web/src/components/ui/calendar.tsx'
    'apps/web/src/components/ui/scroll-area.tsx'
    'apps/web/src/components/ui/command.tsx'
    'apps/web/src/components/ui/collapsible.tsx'
    'apps/web/src/components/layout/sidebar.tsx'
    'apps/web/src/components/layout/header.tsx'
    'apps/web/src/components/layout/mobile-nav.tsx'
    'apps/web/src/components/layout/breadcrumbs.tsx'
    'apps/web/src/components/dashboard/stat-card.tsx'
    'apps/web/src/components/dashboard/upcoming-events-widget.tsx'
    'apps/web/src/components/dashboard/roadmap-phase-summary.tsx'
    'apps/web/src/components/dashboard/quick-actions.tsx'
    'apps/web/src/components/roadmap/phase-card.tsx'
    'apps/web/src/components/roadmap/phase-nav.tsx'
    'apps/web/src/components/roadmap/milestone-toggle.tsx'
    'apps/web/src/components/roadmap/roadmap-progress-bar.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/wizard.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/step-goal.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/step-profile.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/step-cv-upload.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/step-preferences.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/clarification-panel.tsx'
    'apps/web/src/components/roadmap/roadmap-generator/generation-stream.tsx'
    'apps/web/src/components/schedule/weekly-grid.tsx'
    'apps/web/src/components/schedule/weekly-budget-bar.tsx'
    'apps/web/src/components/schedule/habit-row.tsx'
    'apps/web/src/components/schedule/habit-streak-badge.tsx'
    'apps/web/src/components/schedule/habit-heatmap.tsx'
    'apps/web/src/components/progress/weekly-scorecard-form.tsx'
    'apps/web/src/components/progress/metric-chart.tsx'
    'apps/web/src/components/progress/habit-completion-chart.tsx'
    'apps/web/src/components/progress/career-health-score.tsx'
    'apps/web/src/components/cv-analysis/cv-upload-dropzone.tsx'
    'apps/web/src/components/cv-analysis/gap-report-card.tsx'
    'apps/web/src/components/cv-analysis/skill-comparison-table.tsx'
    'apps/web/src/components/cv-analysis/readiness-meter.tsx'
    'apps/web/src/components/market/market-signal-card.tsx'
    'apps/web/src/components/market/trending-skills-chart.tsx'
    'apps/web/src/components/market/salary-benchmark-card.tsx'
    'apps/web/src/components/networking/contact-card.tsx'
    'apps/web/src/components/networking/contact-form.tsx'
    'apps/web/src/components/networking/outreach-log.tsx'
    'apps/web/src/components/networking/event-calendar.tsx'
    'apps/web/src/components/coach/chat-window.tsx'
    'apps/web/src/components/coach/chat-message.tsx'
    'apps/web/src/components/coach/chat-input.tsx'
    'apps/web/src/components/coach/agent-typing-indicator.tsx'
    'apps/web/src/components/shared/page-header.tsx'
    'apps/web/src/components/shared/empty-state.tsx'
    'apps/web/src/components/shared/error-boundary.tsx'
    'apps/web/src/components/shared/loading-spinner.tsx'
    'apps/web/src/components/shared/confirm-dialog.tsx'
    'apps/web/src/components/shared/file-upload.tsx'
    'apps/web/src/components/shared/notification-bell.tsx'
    'apps/web/src/hooks/use-auth.ts'
    'apps/web/src/hooks/use-roadmap.ts'
    'apps/web/src/hooks/use-agent-stream.ts'
    'apps/web/src/hooks/use-clarification.ts'
    'apps/web/src/hooks/use-cv-upload.ts'
    'apps/web/src/hooks/use-market-feed.ts'
    'apps/web/src/hooks/use-habit-log.ts'
    'apps/web/src/hooks/use-weekly-review.ts'
    'apps/web/src/hooks/use-notifications.ts'
    'apps/web/src/hooks/use-debounce.ts'
    'apps/web/src/hooks/use-local-storage.ts'
    'apps/web/src/hooks/use-media-query.ts'
    'apps/web/src/lib/api/client.ts'
    'apps/web/src/lib/api/roadmap.ts'
    'apps/web/src/lib/api/schedule.ts'
    'apps/web/src/lib/api/progress.ts'
    'apps/web/src/lib/api/cv.ts'
    'apps/web/src/lib/api/market.ts'
    'apps/web/src/lib/api/networking.ts'
    'apps/web/src/lib/api/coach.ts'
    'apps/web/src/lib/api/user.ts'
    'apps/web/src/lib/api/notifications.ts'
    'apps/web/src/lib/api/opportunities.ts'
    'apps/web/src/lib/api/books.ts'
    'apps/web/src/lib/api/auth.ts'
    'apps/web/src/lib/websocket.ts'
    'apps/web/src/lib/sse.ts'
    'apps/web/src/lib/auth.ts'
    'apps/web/src/lib/validations.ts'
    'apps/web/src/lib/date.ts'
    'apps/web/src/lib/cn.ts'
    'apps/web/src/lib/constants.ts'
    'apps/web/src/store/auth.store.ts'
    'apps/web/src/store/roadmap.store.ts'
    'apps/web/src/store/agent.store.ts'
    'apps/web/src/store/notification.store.ts'
    'apps/web/src/store/ui.store.ts'
    'apps/web/src/types/api.types.ts'
    'apps/web/src/types/roadmap.types.ts'
    'apps/web/src/types/user.types.ts'
    'apps/web/src/types/agent.types.ts'
    'apps/web/src/types/market.types.ts'
    'apps/web/src/types/networking.types.ts'
    'apps/web/src/types/common.types.ts'
    'apps/web/src/providers/auth-provider.tsx'
    'apps/web/src/providers/query-provider.tsx'
    'apps/web/src/providers/theme-provider.tsx'
    'apps/web/src/providers/toast-provider.tsx'
    'apps/web/src/providers/index.tsx'
    'apps/web/src/styles/globals.css'
    'apps/web/tests/unit/hooks/.gitkeep'
    'apps/web/tests/unit/utils/.gitkeep'
    'apps/web/tests/integration/api-client/.gitkeep'
    'apps/web/tests/e2e/playwright.config.ts'
    'apps/web/tests/e2e/auth.spec.ts'
    'apps/web/tests/e2e/roadmap-generation.spec.ts'
    'apps/web/tests/e2e/clarification-flow.spec.ts'
)

$total   = $files.Count
$created = 0
$skipped = 0
$idx     = 0

Write-Host ''
Write-Host '  Career Roadmap AI -- Frontend Scaffold' -ForegroundColor Cyan
Write-Host "  Root : $Root"                           -ForegroundColor DarkGray
Write-Host '  Mode : safe (no overwrites)'            -ForegroundColor DarkGray
Write-Host ''

foreach ($f in $files) {
    $idx++
    $pct    = [int](($idx / $total) * 100)
    $result = New-ProjectFile -RelPath $f

    Write-Progress -Activity 'Scaffolding frontend' `
                   -Status "$idx / $total -- $f" `
                   -PercentComplete $pct

    if ($result -eq 'created') { $created++ }
    else                        { $skipped++ }
}

Write-Progress -Activity 'Scaffolding frontend' -Completed

Write-Host '  -----------------------------------------' -ForegroundColor DarkGray
Write-Host '  Done!'                                      -ForegroundColor Green
Write-Host ''
Write-Host "  Total checked : $total"                                     -ForegroundColor White
Write-Host "  Created       : $created"                                   -ForegroundColor Green
Write-Host "  Skipped       : $skipped  (already existed, not touched)"   -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Folders scaffolded inside apps/web/src/ :' -ForegroundColor Yellow
Write-Host '    app/(auth)           login, register, forgot-password'     -ForegroundColor DarkGray
Write-Host '    app/(app)            12 authenticated sections'             -ForegroundColor DarkGray
Write-Host '    components/ui        shadcn primitives'                     -ForegroundColor DarkGray
Write-Host '    components/layout    sidebar, header, breadcrumbs'          -ForegroundColor DarkGray
Write-Host '    components/roadmap   phase cards, generator wizard'         -ForegroundColor DarkGray
Write-Host '    components/coach     chat window, message, input'           -ForegroundColor DarkGray
Write-Host '    hooks                12 custom React hooks'                 -ForegroundColor DarkGray
Write-Host '    lib/api              1 file per domain'                     -ForegroundColor DarkGray
Write-Host '    store                5 Zustand stores'                      -ForegroundColor DarkGray
Write-Host '    types                7 TypeScript definition files'         -ForegroundColor DarkGray
Write-Host '    providers            auth, query, theme, toast'             -ForegroundColor DarkGray
Write-Host '    tests/e2e            Playwright spec stubs'                 -ForegroundColor DarkGray
Write-Host ''
Write-Host '  Next: open VS Code and start building!' -ForegroundColor Cyan
Write-Host ''
