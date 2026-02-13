import { useState, useEffect, useMemo } from 'react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { api } from '@/lib/api';
import {
  ChevronLeft,
  Download,
  AlertCircle,
  Layers,
  Clock,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';

interface InterpretationResultsViewProps {
  jobId: string | null;
  protocolId: string | null;
  extraction: any;
  onBack: () => void;
  onExport?: () => void;
}

export function InterpretationResultsView({
  jobId,
  protocolId,
  extraction,
  onBack,
  onExport,
}: InterpretationResultsViewProps) {
  const [stagesData, setStagesData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  // Fetch interpretation stages from database with polling when in progress
  useEffect(() => {
    if (!jobId) {
      setLoading(false);
      return;
    }

    let pollInterval: NodeJS.Timeout | null = null;
    let isMounted = true;

    const fetchStages = async (isInitialFetch: boolean = false) => {
      if (isInitialFetch) {
        setLoading(true);
        setError(null);
      }
      try {
        const response = await api.soa.getInterpretationStages(jobId);

        if (!isMounted) return;

        setStagesData(response);
        // Auto-select first group if available
        if (response.groups && response.groups.length > 0) {
          setSelectedGroup(response.groups[0].merge_group_id);
        }

        // Check if interpretation is still in progress (no groups yet or status is interpreting)
        const isInProgress = !response.groups ||
                            response.groups.length === 0 ||
                            response.status === 'interpreting';

        // If completed, stop polling
        if (!isInProgress && pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
        }

        // Start polling if in progress and not already polling
        if (isInProgress && !pollInterval && isMounted) {
          console.log('[Interpretation] Interpretation in progress, starting poll...');
          pollInterval = setInterval(() => fetchStages(false), 3000);
        }
      } catch (err: any) {
        console.log('[Interpretation] Could not fetch stages:', err.message);
        // Only set error on initial fetch, silently continue polling otherwise
        if (isInitialFetch) {
          setError('Could not load interpretation results');
        }
      } finally {
        if (isInitialFetch) {
          setLoading(false);
        }
      }
    };

    fetchStages(true);

    // Cleanup on unmount
    return () => {
      isMounted = false;
      if (pollInterval) {
        clearInterval(pollInterval);
      }
    };
  }, [jobId]);

  // Get selected group data
  const selectedGroupData = useMemo(() => {
    if (!stagesData?.groups || !selectedGroup) return null;
    return stagesData.groups.find((g: any) => g.merge_group_id === selectedGroup);
  }, [stagesData, selectedGroup]);

  // Stage metadata from response
  const stageMetadata = stagesData?.stage_metadata || {};

  // Stage status colors
  const getStageStatusColor = (status: string) => {
    switch (status) {
      case 'success': return 'bg-green-100 text-green-700 border-green-200';
      case 'failed': return 'bg-red-100 text-red-700 border-red-200';
      case 'skipped': return 'bg-gray-100 text-gray-500 border-gray-200';
      default: return 'bg-yellow-100 text-yellow-700 border-yellow-200';
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={onBack}
              className="h-9 px-3"
            >
              <ChevronLeft className="w-4 h-4 mr-1" />
              Back to Review
            </Button>
            <div className="h-6 w-px bg-gray-200" />
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-primary/10">
                <Layers className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gray-800">Interpretation Results</h1>
                <p className="text-sm text-gray-500">
                  12-stage USDM interpretation pipeline
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {onExport && (
              <Button
                variant="outline"
                size="sm"
                onClick={onExport}
                className="h-9 px-3"
              >
                <Download className="w-4 h-4 mr-2" />
                Export SOA USDM
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Content Area */}
      <ScrollArea className="flex-1">
        <div className="p-6 max-w-5xl mx-auto">
          {/* Loading State */}
          {loading && (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
              <Loader2 className="w-8 h-8 text-primary mx-auto mb-3 animate-spin" />
              <p className="text-gray-700 font-medium">Loading interpretation results...</p>
              <p className="text-sm text-gray-500 mt-1">Fetching stage-by-stage data</p>
            </div>
          )}

          {/* Error State */}
          {!loading && error && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
              <AlertCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
              <p className="text-red-800 font-medium">{error}</p>
              <p className="text-sm text-red-600 mt-1">Please try again or check the job status</p>
              <Button variant="outline" onClick={onBack} className="mt-4">
                Go Back
              </Button>
            </div>
          )}

          {/* No Job ID */}
          {!loading && !error && !jobId && (
            <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center">
              <AlertCircle className="w-10 h-10 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-700 font-medium">No interpretation job found</p>
              <p className="text-sm text-gray-500 mt-1">Start an extraction to see results</p>
              <Button variant="outline" onClick={onBack} className="mt-4">
                Go Back
              </Button>
            </div>
          )}

          {/* No Data Yet */}
          {!loading && !error && jobId && (!stagesData || !stagesData.groups || stagesData.groups.length === 0) && (
            <div className="rounded-2xl bg-amber-50 border border-amber-200 p-6">
              <div className="flex items-start gap-3">
                <Clock className="w-6 h-6 text-amber-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-lg font-medium text-amber-800">Interpretation in Progress</p>
                  <p className="text-sm text-amber-700 mt-1">
                    The 12-stage interpretation pipeline is processing. Results will appear here when complete.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Full Results View */}
          {!loading && !error && stagesData && stagesData.groups && stagesData.groups.length > 0 && (
            <div className="space-y-6">
              {/* Group Selector (if multiple groups) */}
              {stagesData.groups.length > 1 && (
                <div className="flex gap-2 flex-wrap">
                  {stagesData.groups.map((group: any) => (
                    <Button
                      key={group.merge_group_id}
                      variant={selectedGroup === group.merge_group_id ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setSelectedGroup(group.merge_group_id)}
                    >
                      {group.merge_group_id}
                      <span className="ml-2 text-xs opacity-70">
                        ({group.source_table_ids?.join(', ')})
                      </span>
                    </Button>
                  ))}
                </div>
              )}

              {/* Hero CTA for Detailed Insights */}
              {protocolId && (
                <div className="rounded-2xl bg-gradient-to-br from-zinc-800 to-zinc-900 p-6 text-white shadow-xl ring-1 ring-white/10">
                  <div className="flex items-center justify-between">
                    <div className="space-y-2">
                      <h3 className="text-xl font-semibold tracking-tight flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-zinc-300" />
                        Ready to Explore Your Results?
                      </h3>
                      <p className="text-zinc-400 text-sm max-w-md">
                        View detailed activity breakdowns, timing analysis, and USDM compliance insights for this protocol.
                      </p>
                    </div>
                    <a
                      href={`/insights?studyId=${encodeURIComponent(protocolId)}`}
                      className="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold text-zinc-900 bg-white/95 backdrop-blur rounded-full hover:bg-white shadow-md hover:shadow-lg transition-all flex-shrink-0"
                    >
                      View Detailed Insights
                      <ArrowRight className="w-4 h-4" />
                    </a>
                  </div>
                </div>
              )}

              {/* Selected Group Details */}
              {selectedGroupData && (
                <div className="space-y-4">
                  {/* Summary Card */}
                  <div className="rounded-xl bg-gray-50 border border-gray-200 p-4">
                    <div className="grid grid-cols-4 gap-4 text-center">
                      <div>
                        <p className="text-2xl font-bold text-green-600">
                          {selectedGroupData.interpretation_summary?.stages_completed || 0}
                        </p>
                        <p className="text-xs text-gray-500">Completed</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-red-600">
                          {selectedGroupData.interpretation_summary?.stages_failed || 0}
                        </p>
                        <p className="text-xs text-gray-500">Failed</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-gray-400">
                          {selectedGroupData.interpretation_summary?.stages_skipped || 0}
                        </p>
                        <p className="text-xs text-gray-500">Skipped</p>
                      </div>
                      <div>
                        <p className="text-2xl font-bold text-zinc-500">
                          {(selectedGroupData.interpretation_summary?.total_duration_seconds || 0).toFixed(1)}s
                        </p>
                        <p className="text-xs text-gray-500">Duration</p>
                      </div>
                    </div>
                  </div>

                  {/* Stage-by-Stage Results */}
                  <div className="space-y-2">
                    <h4 className="font-medium text-gray-700 px-1">Stage Results</h4>
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((stageNum) => {
                      const stageMeta = stageMetadata[stageNum] || { name: `Stage ${stageNum}`, description: '' };
                      const stageStatus = selectedGroupData.interpretation_summary?.stage_statuses?.[stageNum] || 'pending';
                      const stageDuration = selectedGroupData.interpretation_summary?.stage_durations?.[stageNum];
                      const stageResult = selectedGroupData.stage_results?.[stageNum];

                      return (
                        <div
                          key={stageNum}
                          className="rounded-lg border border-gray-200 bg-white p-3 hover:shadow-sm transition-shadow"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs font-medium text-gray-600">
                                {stageNum}
                              </span>
                              <div>
                                <p className="font-medium text-gray-900 text-sm">{stageMeta.name}</p>
                                <p className="text-xs text-gray-500">{stageMeta.description}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2">
                              {stageDuration !== undefined && (
                                <span className="text-xs text-gray-400">{stageDuration.toFixed(2)}s</span>
                              )}
                              <span className={cn(
                                "px-2 py-0.5 rounded-full text-[10px] font-medium border",
                                getStageStatusColor(stageStatus)
                              )}>
                                {stageStatus}
                              </span>
                            </div>
                          </div>

                          {/* Show stage result summary if available */}
                          {stageResult && typeof stageResult === 'object' && (
                            <div className="mt-2 pt-2 border-t border-gray-100">
                              {stageResult.summary && (
                                <p className="text-xs text-gray-600">{stageResult.summary}</p>
                              )}
                              {stageResult.changesApplied !== undefined && (
                                <p className="text-xs text-gray-500">Changes applied: {stageResult.changesApplied}</p>
                              )}
                              {stageResult.activitiesProcessed !== undefined && (
                                <p className="text-xs text-gray-500">Activities processed: {stageResult.activitiesProcessed}</p>
                              )}
                              {stageResult.expansionsCount !== undefined && (
                                <p className="text-xs text-gray-500">Expansions: {stageResult.expansionsCount}</p>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {/* Counts Summary */}
                  {selectedGroupData.counts && (
                    <div className="rounded-xl bg-blue-50 border border-blue-200 p-4">
                      <h4 className="font-medium text-blue-900 mb-2">Final Output Counts</h4>
                      <div className="grid grid-cols-4 gap-4 text-center">
                        <div>
                          <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.visits || 0}</p>
                          <p className="text-xs text-blue-600">Visits</p>
                        </div>
                        <div>
                          <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.activities || 0}</p>
                          <p className="text-xs text-blue-600">Activities</p>
                        </div>
                        <div>
                          <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.sais || 0}</p>
                          <p className="text-xs text-blue-600">SAIs</p>
                        </div>
                        <div>
                          <p className="text-xl font-bold text-blue-700">{selectedGroupData.counts.footnotes || 0}</p>
                          <p className="text-xs text-blue-600">Footnotes</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
