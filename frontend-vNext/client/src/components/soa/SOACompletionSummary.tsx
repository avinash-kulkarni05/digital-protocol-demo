import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  CheckCircle2,
  Download,
  Table2,
  Layers,
  Calendar,
  ClipboardCheck,
  FileText,
  Eye,
  ArrowRight,
  Sparkles,
  Cog,
  GitMerge,
  FileStack,
} from 'lucide-react';
import type { MergePlan } from '@/lib/api';

interface SOACompletionSummaryProps {
  studyId: string;
  extraction: any;
  mergePlan: MergePlan | null;
  mergedResults: any | null;
  onExportExtracted: () => void;
  onExportInterpreted: () => void;
  onViewDetails: () => void;
}

export function SOACompletionSummary({
  studyId,
  extraction,
  mergePlan,
  mergedResults,
  onExportExtracted,
  onExportInterpreted,
  onViewDetails,
}: SOACompletionSummaryProps) {
  const tables = extraction?.tables || [];
  const totalTables = tables.length;
  const mergedGroups = mergedResults?.groups || [];
  const hasMergedData = mergedGroups.length > 0;

  // Per-table stats lookup (from extraction data)
  const perTableStats: Record<string, { encounters: number; activities: number; sais: number; footnotes: number }> = {};
  tables.forEach((t: any) => {
    const tid = t.id || t.tableId;
    perTableStats[tid] = {
      encounters: t.visits?.length || 0,
      activities: t.activities?.length || 0,
      sais: t.matrix?.grid ? Object.values(t.matrix.grid as Record<string, Record<string, string>>).reduce(
        (sum: number, row: any) => sum + Object.values(row).filter((v: any) => v && v !== '').length, 0
      ) : 0,
      footnotes: t.footnotes?.length || 0,
    };
  });

  // Merged totals
  const mergedTotals = hasMergedData ? {
    encounters: mergedGroups.reduce((s: number, g: any) => s + (g.usdm?.encounters?.length || 0), 0),
    activities: mergedGroups.reduce((s: number, g: any) => s + (g.usdm?.activities?.length || 0), 0),
    sais: mergedGroups.reduce((s: number, g: any) => s + (g.usdm?.scheduledActivityInstances?.length || 0), 0),
    footnotes: mergedGroups.reduce((s: number, g: any) => s + (g.usdm?.footnotes?.length || 0), 0),
  } : null;

  // Pre-merge totals (sum of individual tables)
  const preMergeTotals = {
    encounters: Object.values(perTableStats).reduce((s, t) => s + t.encounters, 0),
    activities: Object.values(perTableStats).reduce((s, t) => s + t.activities, 0),
    footnotes: Object.values(perTableStats).reduce((s, t) => s + t.footnotes, 0),
  };

  const mergeGroups = mergePlan?.mergeGroups || [];

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-auto">
      <div className="max-w-5xl mx-auto w-full py-8 px-6 space-y-6">

        {/* Hero Banner */}
        <Card className="border-green-200 bg-gradient-to-r from-green-50 to-emerald-50">
          <CardContent className="py-6">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-6 h-6 text-green-600" />
              </div>
              <div className="flex-1">
                <h1 className="text-lg font-semibold text-green-800">
                  SOA Analysis Complete
                </h1>
                <p className="text-sm text-green-600 mt-0.5">
                  {studyId} &mdash; {totalTables} table{totalTables !== 1 ? 's' : ''} extracted, interpreted{hasMergedData ? ', and merged' : ''}
                </p>
              </div>
              <div className="flex gap-2 shrink-0">
                <Button variant="outline" size="sm" onClick={onExportExtracted} className="gap-1.5 text-xs">
                  <Download className="w-3.5 h-3.5" />
                  Extracted
                </Button>
                <Button size="sm" onClick={onExportInterpreted} className="gap-1.5 text-xs">
                  <Download className="w-3.5 h-3.5" />
                  Merged USDM
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Before → After Overview (only if merged data available) */}
        {hasMergedData && mergedTotals && (
          <Card className="border-gray-200">
            <CardContent className="p-0">
              <div className="grid grid-cols-[1fr,auto,1fr] items-stretch">
                {/* Before */}
                <div className="p-5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">Before Merge</p>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="text-2xl font-bold text-gray-400">{preMergeTotals.encounters}</p>
                      <p className="text-xs text-muted-foreground">Encounters</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-gray-400">{preMergeTotals.activities}</p>
                      <p className="text-xs text-muted-foreground">Activities</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-gray-400">{preMergeTotals.footnotes}</p>
                      <p className="text-xs text-muted-foreground">Footnotes</p>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">Sum of {totalTables} individual tables</p>
                </div>

                {/* Arrow divider */}
                <div className="flex items-center justify-center px-3 bg-gray-50 border-x border-gray-100">
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </div>

                {/* After */}
                <div className="p-5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">After Merge</p>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <p className="text-2xl font-bold text-gray-900">{mergedTotals.encounters}</p>
                      <p className="text-xs text-muted-foreground">Encounters</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-gray-900">{mergedTotals.activities}</p>
                      <p className="text-xs text-muted-foreground">Activities</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-gray-900">{mergedTotals.footnotes}</p>
                      <p className="text-xs text-muted-foreground">Footnotes</p>
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    {mergedTotals.sais} scheduled activity instances &middot; {mergedGroups.length} group{mergedGroups.length !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Per-Group Details */}
        {hasMergedData ? (
          <div className="space-y-4">
            {mergedGroups.map((group: any) => {
              const usdm = group.usdm || {};
              const meta = usdm._mergeMetadata || {};
              const tableIds: string[] = group.tableIds || [];
              const isStandalone = tableIds.length <= 1;
              const mergeMethod = meta.mergeMethod || 'unknown';

              const counts = {
                encounters: usdm.encounters?.length || 0,
                activities: usdm.activities?.length || 0,
                sais: usdm.scheduledActivityInstances?.length || 0,
                footnotes: usdm.footnotes?.length || 0,
              };

              return (
                <Card key={group.groupId} className={cn(
                  isStandalone ? 'border-gray-200' : 'border-blue-200'
                )}>
                  <CardContent className="p-0">
                    {/* Group header */}
                    <div className={cn(
                      'flex items-center gap-3 px-4 py-3 border-b',
                      isStandalone ? 'bg-gray-50/50 border-gray-100' : 'bg-blue-50/50 border-blue-100'
                    )}>
                      {isStandalone
                        ? <FileStack className="w-4 h-4 text-gray-400 shrink-0" />
                        : <GitMerge className="w-4 h-4 text-blue-500 shrink-0" />
                      }
                      <span className="text-sm font-semibold text-gray-800">{group.groupId}</span>
                      <div className="flex gap-1.5 flex-1">
                        {tableIds.map((tid: string) => (
                          <Badge key={tid} variant="secondary" className="text-xs font-medium">{tid}</Badge>
                        ))}
                      </div>
                      <MergeMethodBadge method={mergeMethod} isStandalone={isStandalone} />
                    </div>

                    <div className="p-4 space-y-4">
                      {/* Per-source-table breakdown for merged groups */}
                      {!isStandalone && tableIds.length > 1 && (
                        <div className="space-y-2">
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Source Tables</p>
                          <div className="grid gap-2">
                            {tableIds.map((tid: string) => {
                              const stats = perTableStats[tid] || { encounters: 0, activities: 0, sais: 0, footnotes: 0 };
                              return (
                                <div key={tid} className="flex items-center gap-3 px-3 py-2 rounded-md bg-gray-50 border border-gray-100">
                                  <span className="text-sm font-medium text-gray-700 w-14">{tid}</span>
                                  <div className="flex gap-4 text-xs text-muted-foreground">
                                    <span><span className="font-semibold text-gray-600">{stats.encounters}</span> encounters</span>
                                    <span><span className="font-semibold text-gray-600">{stats.activities}</span> activities</span>
                                    <span><span className="font-semibold text-gray-600">{stats.footnotes}</span> footnotes</span>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Merged result counts */}
                      <div>
                        {!isStandalone && (
                          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">Merged Result</p>
                        )}
                        <div className={cn(
                          'rounded-lg p-3',
                          isStandalone ? 'bg-gray-50 border border-gray-100' : 'bg-blue-50/60 border border-blue-100'
                        )}>
                          <div className="grid grid-cols-4 gap-4 text-center">
                            <CountCell label="Encounters" value={counts.encounters} color={isStandalone ? 'gray' : 'blue'} />
                            <CountCell label="Activities" value={counts.activities} color={isStandalone ? 'gray' : 'blue'} />
                            <CountCell label="SAIs" value={counts.sais} color={isStandalone ? 'gray' : 'blue'} />
                            <CountCell label="Footnotes" value={counts.footnotes} color={isStandalone ? 'gray' : 'blue'} />
                          </div>
                        </div>
                      </div>

                      {/* Deduplication summary for merged groups */}
                      {!isStandalone && tableIds.length > 1 && (() => {
                        const srcEncTotal = tableIds.reduce((s: number, tid: string) => s + (perTableStats[tid]?.encounters || 0), 0);
                        const srcActTotal = tableIds.reduce((s: number, tid: string) => s + (perTableStats[tid]?.activities || 0), 0);
                        const encDelta = srcEncTotal - counts.encounters;
                        const actDelta = srcActTotal - counts.activities;
                        if (encDelta <= 0 && actDelta <= 0) return null;
                        return (
                          <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
                            <CheckCircle2 className="w-3.5 h-3.5 text-green-500 shrink-0" />
                            <span>
                              {encDelta > 0 && <><span className="font-medium text-green-700">{encDelta} duplicate encounter{encDelta !== 1 ? 's' : ''}</span> resolved</>}
                              {encDelta > 0 && actDelta > 0 && ', '}
                              {actDelta > 0 && <><span className="font-medium text-green-700">{actDelta} duplicate activit{actDelta !== 1 ? 'ies' : 'y'}</span> resolved</>}
                              {' '}across tables
                            </span>
                          </div>
                        );
                      })()}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : mergeGroups.length > 0 ? (
          /* Fallback: simple merge groups when no merged data */
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">Merge Groups</h2>
            <div className="space-y-2">
              {mergeGroups.map((group) => {
                const isStandalone = group.mergeType === 'standalone' || group.tableIds.length === 1;
                return (
                  <div key={group.id} className={cn(
                    'flex items-center gap-3 px-4 py-3 bg-white rounded-lg border',
                    isStandalone ? 'border-gray-200' : 'border-blue-200'
                  )}>
                    <Layers className={cn('w-4 h-4 shrink-0', isStandalone ? 'text-gray-400' : 'text-blue-500')} />
                    <span className="text-sm font-medium text-gray-700 min-w-[60px]">{group.id}</span>
                    <div className="flex gap-1.5 flex-wrap flex-1">
                      {group.tableIds.map((tid) => (
                        <Badge key={tid} variant="secondary" className="text-xs">{tid}</Badge>
                      ))}
                    </div>
                    <Badge variant="outline" className={cn(
                      'text-xs shrink-0',
                      isStandalone ? 'text-gray-500' : 'text-blue-600 border-blue-200'
                    )}>
                      {isStandalone ? 'standalone' : group.mergeType.replace(/_/g, ' ')}
                    </Badge>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {/* View Details */}
        <div className="flex justify-center pt-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground gap-2"
            onClick={onViewDetails}
          >
            <Eye className="w-4 h-4" />
            View Extraction Details
          </Button>
        </div>
      </div>
    </div>
  );
}

function MergeMethodBadge({ method, isStandalone }: { method: string; isStandalone: boolean }) {
  if (isStandalone) {
    return (
      <Badge variant="outline" className="text-xs text-gray-500 shrink-0">
        Standalone
      </Badge>
    );
  }
  if (method === 'llm_claude') {
    return (
      <Badge className="text-xs bg-green-100 text-green-700 border border-green-200 hover:bg-green-100 gap-1 shrink-0">
        <Sparkles className="w-3 h-3" />
        AI Merged (Claude)
      </Badge>
    );
  }
  if (method === 'llm_gemini') {
    return (
      <Badge className="text-xs bg-blue-100 text-blue-700 border border-blue-200 hover:bg-blue-100 gap-1 shrink-0">
        <Sparkles className="w-3 h-3" />
        AI Merged (Gemini)
      </Badge>
    );
  }
  if (method === 'naive_with_prefixing') {
    return (
      <Badge className="text-xs bg-amber-100 text-amber-700 border border-amber-200 hover:bg-amber-100 gap-1 shrink-0">
        <Cog className="w-3 h-3" />
        Auto Merged
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-xs text-blue-600 border-blue-200 gap-1 shrink-0">
      <Layers className="w-3 h-3" />
      Merged
    </Badge>
  );
}

function CountCell({ label, value, color }: { label: string; value: number; color: 'blue' | 'gray' }) {
  return (
    <div>
      <p className={cn(
        'text-xl font-bold',
        color === 'blue' ? 'text-blue-700' : 'text-gray-700'
      )}>{value}</p>
      <p className={cn(
        'text-xs',
        color === 'blue' ? 'text-blue-600/70' : 'text-muted-foreground'
      )}>{label}</p>
    </div>
  );
}
