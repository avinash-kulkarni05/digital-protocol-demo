import { motion } from "framer-motion";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Header } from "@/components/layout/Header";
import { FileText, Upload, Sparkles, Eye, Calendar, ChevronRight, Loader2 } from "lucide-react";
import { useAllDocuments } from "@/lib/queries";
import { useState, useRef, useEffect, useCallback } from "react";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

export default function LandingPage() {
  const { data: documents, isLoading } = useAllDocuments();
  const queryClient = useQueryClient();
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [extractingProtocols, setExtractingProtocols] = useState<Set<string>>(new Set());
  const [extractionProgress, setExtractionProgress] = useState<Map<string, number>>(new Map());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [pollingJobs, setPollingJobs] = useState<Set<string>>(new Set());

  // Poll progress for a specific job
  const pollJobProgress = useCallback(async (protocolId: string, jobId: string, studyId: string) => {
    try {
      const status = await api.extraction.getJobStatus(jobId);
      console.log('[Progress Poll]', { protocolId, jobId, status: status.status, completed: status.completed_modules?.length, total: status.total_modules });

      const completedCount = status.completed_modules?.length || 0;
      const totalCount = status.total_modules || 16;
      const progressPercent = Math.round((completedCount / totalCount) * 100);

      setExtractionProgress(prev => {
        const next = new Map(prev);
        next.set(protocolId, progressPercent);
        return next;
      });

      if (status.status === 'completed' || status.status === 'completed_with_errors') {
        // Stop polling
        setPollingJobs(prev => {
          const next = new Set(prev);
          next.delete(protocolId);
          return next;
        });
        // Clear progress
        setExtractionProgress(prev => {
          const next = new Map(prev);
          next.delete(protocolId);
          return next;
        });
        // Show toast notification
        const hasErrors = status.status === 'completed_with_errors';
        toast({
          title: hasErrors ? "Extraction Completed with Errors" : "Extraction Complete",
          description: hasErrors
            ? `${studyId} is ready for review (some modules failed)`
            : `${studyId} is ready for review`,
        });
        // Refetch documents
        queryClient.invalidateQueries({ queryKey: ["documents"] });
        // Navigate to review page
        setLocation(`/review/study_metadata?studyId=${encodeURIComponent(studyId)}&protocolId=${encodeURIComponent(protocolId)}`);
      } else if (status.status === 'failed') {
        // Stop polling on failure
        setPollingJobs(prev => {
          const next = new Set(prev);
          next.delete(protocolId);
          return next;
        });
        setExtractionProgress(prev => {
          const next = new Map(prev);
          next.delete(protocolId);
          return next;
        });
        toast({
          title: "Extraction Failed",
          description: `Failed to process ${studyId}. Please try again.`,
          variant: "destructive",
        });
        queryClient.invalidateQueries({ queryKey: ["documents"] });
      } else {
        // Continue polling
        setTimeout(() => pollJobProgress(protocolId, jobId, studyId), 5000);
      }
    } catch (error) {
      console.error('Poll error:', error);
      setPollingJobs(prev => {
        const next = new Set(prev);
        next.delete(protocolId);
        return next;
      });
    }
  }, [queryClient, toast, setLocation]);

  // Start polling for protocols that are already processing
  useEffect(() => {
    if (!documents) return;

    documents.forEach(async (doc) => {
      const status = (doc as any).extractionStatus;
      const protocolId = String(doc.id);
      const studyId = doc.studyId;

      // If processing and not already polling
      if (status === 'processing' && !pollingJobs.has(protocolId) && !extractingProtocols.has(protocolId)) {
        try {
          const latestJob = await api.extraction.getLatestJob(protocolId);
          console.log('[Latest Job]', { protocolId, studyId, latestJob });

          if (latestJob.job_id && (latestJob.status === 'running' || latestJob.status === 'pending')) {
            setPollingJobs(prev => new Set(prev).add(protocolId));
            pollJobProgress(protocolId, latestJob.job_id, studyId);
          }
        } catch (error) {
          console.error('Failed to get latest job:', error);
        }
      }
    });
  }, [documents, pollingJobs, extractingProtocols, pollJobProgress]);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const uploadFile = async (file: File) => {
    if (!file.type.includes('pdf')) {
      toast({
        title: "Invalid file type",
        description: "Please upload a PDF file",
        variant: "destructive",
      });
      return;
    }

    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/api/backend/protocols/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const data = await response.json();

      toast({
        title: "Upload successful",
        description: `${file.name} has been uploaded successfully. Click the protocol card to start extraction.`,
      });

      // Refetch protocols list to show the newly uploaded protocol
      await queryClient.invalidateQueries({ queryKey: ["documents"] });

    } catch (error) {
      console.error('Upload error:', error);
      toast({
        title: "Upload failed",
        description: "Failed to upload protocol. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      uploadFile(files[0]);
    }
  };

  const handleStartExtraction = async (protocolId: string, studyId: string) => {
    setExtractingProtocols(prev => new Set(prev).add(protocolId));

    try {
      const result = await api.extraction.startExtraction(protocolId);

      toast({
        title: "Extraction Started",
        description: `Processing ${studyId}. This may take 20-30 minutes.`,
      });

      // Poll for completion (simplified - in production, use SSE or WebSocket)
      const checkStatus = async () => {
        try {
          const status = await api.extraction.getJobStatus(result.job_id);
          console.log('[Progress Poll]', { jobId: result.job_id, status: status.status, completed: status.completed_modules, total: status.total_modules });

          // Update progress percentage
          const completedCount = status.completed_modules?.length || 0;
          const totalCount = status.total_modules || 16;
          const progressPercent = Math.round((completedCount / totalCount) * 100);
          console.log('[Progress]', { protocolId, completedCount, totalCount, progressPercent });
          setExtractionProgress(prev => {
            const next = new Map(prev);
            next.set(protocolId, progressPercent);
            return next;
          });

          if (status.status === 'completed' || status.status === 'completed_with_errors') {
            const hasErrors = status.status === 'completed_with_errors';
            toast({
              title: hasErrors ? "Extraction Completed with Errors" : "Extraction Complete",
              description: hasErrors
                ? `${studyId} is ready for review (some modules failed)`
                : `${studyId} is ready for review`,
            });
            setExtractingProtocols(prev => {
              const next = new Set(prev);
              next.delete(protocolId);
              return next;
            });
            // Clear progress
            setExtractionProgress(prev => {
              const next = new Map(prev);
              next.delete(protocolId);
              return next;
            });
            // Refetch protocols to show updated USDM data and status
            queryClient.invalidateQueries({ queryKey: ["documents"] });
            // Redirect to review page with both studyId and protocolId
            setLocation(`/review/study_metadata?studyId=${encodeURIComponent(studyId)}&protocolId=${encodeURIComponent(protocolId)}`);
          } else if (status.status === 'failed') {
            // Handle failure gracefully
            toast({
              title: "Extraction Failed",
              description: `Failed to process ${studyId}. Please try again.`,
              variant: "destructive",
            });
            setExtractingProtocols(prev => {
              const next = new Set(prev);
              next.delete(protocolId);
              return next;
            });
            // Clear progress
            setExtractionProgress(prev => {
              const next = new Map(prev);
              next.delete(protocolId);
              return next;
            });
          } else {
            // Still running, check again in 5 seconds (faster for better UX)
            setTimeout(checkStatus, 5000);
          }
        } catch (error) {
          console.error('Status check error:', error);
          // Remove from extracting state on error
          setExtractingProtocols(prev => {
            const next = new Set(prev);
            next.delete(protocolId);
            return next;
          });
        }
      };

      // Start polling quickly (3 seconds), then every 5 seconds
      setTimeout(checkStatus, 3000);

    } catch (error) {
      console.error('Extraction error:', error);
      toast({
        title: "Extraction Failed",
        description: "Failed to start extraction. Please try again.",
        variant: "destructive",
      });
      setExtractingProtocols(prev => {
        const next = new Set(prev);
        next.delete(protocolId);
        return next;
      });
    }
  };

  return (
    <div className="min-h-full bg-gradient-to-b from-gray-50/50 to-white">
      <Header title="Digital Study Platform" />
      
      <motion.section
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="pt-20 pb-16 px-8"
      >
        <div className="max-w-4xl mx-auto text-center">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.6 }}
            className="text-5xl md:text-6xl font-bold tracking-tight text-foreground mb-4"
            data-testid="hero-title"
          >
            Intelligent Protocol
            <br />
            Conversion
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.6 }}
            className="text-sm font-medium tracking-widest text-muted-foreground uppercase mb-6"
            data-testid="hero-subtitle"
          >
            From PDF to USDM 4.0 in minutes
          </motion.p>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.6 }}
            className="text-lg text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed"
            data-testid="hero-description"
          >
            Agentic AI that reasons, plans, and acts autonomously to extract, structure,
            and standardize clinical protocol data with human-in-the-loop verification.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.6 }}
            className="flex flex-wrap items-center justify-center gap-4"
          >
            <Link href={documents && documents.length > 0 ? `/review/study_metadata?studyId=${encodeURIComponent(documents[0].studyId)}` : "/review/study_metadata"}>
              <Button
                size="lg"
                className="px-8 py-6 text-base font-medium rounded-full bg-foreground text-background hover:bg-foreground/90 shadow-lg shadow-foreground/10"
                data-testid="button-launch-agent"
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Launch Protocol Agent
              </Button>
            </Link>
            <Link href={documents && documents.length > 0 ? `/review/quality_management?studyId=${encodeURIComponent(documents[0].studyId)}` : "/review/quality_management"}>
              <Button
                variant="outline"
                size="lg"
                className="px-8 py-6 text-base font-medium rounded-full border-2 hover:bg-gray-50"
                data-testid="button-explore-capabilities"
              >
                Explore Capabilities
              </Button>
            </Link>
          </motion.div>
        </div>
      </motion.section>

      <motion.section
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="py-16 px-8"
      >
        <div className="max-w-6xl mx-auto">
          <motion.div variants={itemVariants} className="text-center mb-12">
            <h2
              className="text-2xl md:text-3xl font-bold tracking-tight text-foreground mb-3"
              data-testid="section-title-protocols"
            >
              Digitalized Protocols
            </h2>
            <p className="text-muted-foreground max-w-xl mx-auto">
              Clinical trial protocols that have been processed and converted to structured USDM format.
            </p>
          </motion.div>

          {isLoading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-foreground" data-testid="loading-spinner" />
            </div>
          ) : documents && documents.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-12">
              {documents.map((doc) => {
                const usdm = doc.usdmData as any;
                const study = usdm?.study;
                const status = (doc as any).extractionStatus;
                const isCompleted = status === 'completed' || status === 'completed_with_errors';
                const isProcessing = extractingProtocols.has(String(doc.id)) || pollingJobs.has(String(doc.id)) || status === 'processing';
                const progressPercent = extractionProgress.get(String(doc.id)) || 0;

                // Get study acronym/short name (e.g., ADAURA)
                const studyAcronym = study?.name || doc.studyId;

                // Get sponsor name
                const sponsorName = study?.sponsorName?.value;

                // Get official title
                const officialTitle = study?.officialTitle || doc.studyTitle;

                // Get protocol ID from sponsor identifier (e.g., D5164C00001)
                const protocolId = study?.studyIdentifiers?.find((id: any) =>
                  id?.scopeId?.toLowerCase() === 'sponsor'
                )?.id || study?.id || doc.studyId;

                // Get phase decode
                const phaseText = study?.studyPhase?.decode;

                // Get therapeutic area
                const therapeuticArea = study?.therapeuticArea?.value;

                // Get indication
                const indication = study?.indication?.value;

                // Get date (backend returns created_at)
                const createdAt = (doc as any).created_at || doc.createdAt;
                const displayDate = createdAt
                  ? new Date(createdAt).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric'
                    })
                  : 'Recently added';

                return (
                  <motion.div
                    key={doc.id}
                    variants={itemVariants}
                    whileHover={{ y: -4, transition: { duration: 0.2 } }}
                    className="relative p-6 rounded-xl border border-gray-200 bg-white shadow-sm hover:shadow-md transition-all duration-300 group flex flex-col h-full overflow-hidden"
                    data-testid={`card-protocol-${doc.id}`}
                  >
                    {/* Dark top border accent */}
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gray-800 rounded-t-xl" />

                    {/* Top section: Icon and Status */}
                    <div className="flex items-start justify-between mb-4 mt-2">
                      <div className="w-11 h-11 rounded-lg bg-gray-100 flex items-center justify-center">
                        {isProcessing ? (
                          <Loader2 className="w-5 h-5 text-gray-600 animate-spin" />
                        ) : (
                          <FileText className="w-5 h-5 text-gray-600" />
                        )}
                      </div>
                      <span className="flex items-center gap-1.5">
                        {isProcessing ? (
                          <>
                            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                            <span className="text-xs font-medium text-blue-600">
                              {progressPercent > 0 ? `${progressPercent}%` : 'Processing...'}
                            </span>
                          </>
                        ) : isCompleted ? (
                          <>
                            <span className="w-2 h-2 rounded-full bg-gray-800" />
                            <span className="text-xs font-medium text-gray-700">Ready for Review</span>
                          </>
                        ) : (
                          <>
                            <span className="w-2 h-2 rounded-full bg-gray-400" />
                            <span className="text-xs font-medium text-gray-500">Pending Extraction</span>
                          </>
                        )}
                      </span>
                    </div>

                    {/* Study Name and Sponsor Badge */}
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <h3
                        className="font-bold text-gray-900 text-xl"
                        data-testid={`text-protocol-name-${doc.id}`}
                      >
                        {studyAcronym}
                      </h3>
                      {sponsorName && (
                        <span
                          className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-gray-100 text-gray-700 border border-gray-200"
                          data-testid={`badge-sponsor-${doc.id}`}
                        >
                          {sponsorName}
                        </span>
                      )}
                    </div>

                    {/* Official Title */}
                    <p
                      className="text-sm text-gray-500 mb-1 line-clamp-2"
                      data-testid={`text-protocol-title-${doc.id}`}
                    >
                      {officialTitle}
                    </p>

                    {/* Protocol ID / NCT ID */}
                    <p
                      className="text-xs text-gray-400 mb-2"
                      data-testid={`text-protocol-id-${doc.id}`}
                    >
                      {protocolId}
                    </p>

                    {/* Phase and Therapeutic Area Badges */}
                    <div className="flex flex-wrap gap-2 mb-2">
                      {phaseText && (
                        <span
                          className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-gray-800 text-white"
                          data-testid={`badge-phase-${doc.id}`}
                        >
                          {phaseText}
                        </span>
                      )}
                      {therapeuticArea && (
                        <span
                          className="px-2.5 py-0.5 text-xs font-medium rounded-full border border-gray-300 text-gray-600"
                          data-testid={`badge-therapeutic-${doc.id}`}
                        >
                          {therapeuticArea}
                        </span>
                      )}
                    </div>

                    {/* Indication Highlight Box */}
                    {indication && (
                      <div
                        className="p-3 mb-3 rounded-md bg-gray-50"
                        data-testid={`indication-box-${doc.id}`}
                      >
                        <p className="text-sm text-gray-600 leading-relaxed line-clamp-3">
                          {indication}
                        </p>
                      </div>
                    )}

                    {/* Date */}
                    <div className="flex items-center text-xs text-gray-400 mb-4">
                      <Calendar className="w-3.5 h-3.5 mr-1.5" />
                      {displayDate}
                    </div>

                    {/* Spacer */}
                    <div className="flex-grow" />

                    {/* Review Protocol Button */}
                    <button
                      onClick={() => {
                        if (isCompleted) {
                          setLocation(`/review/study_metadata?studyId=${encodeURIComponent(doc.studyId)}`);
                        } else if (!isProcessing) {
                          handleStartExtraction(String(doc.id), doc.studyId);
                        }
                      }}
                      className={`relative w-full flex items-center justify-between px-4 py-2.5 rounded-full border border-gray-200 bg-white overflow-hidden transition-all duration-200 group/btn ${
                        !isProcessing ? 'hover:bg-gray-900 hover:border-gray-900 hover:text-white' : ''
                      }`}
                      data-testid={`button-review-${doc.id}`}
                    >
                      {/* Progress bar fill */}
                      {isProcessing && (
                        <div
                          className="absolute left-0 top-0 bottom-0 bg-gray-100 transition-all duration-500 ease-out"
                          style={{ width: `${progressPercent}%` }}
                        />
                      )}
                      <div className="relative flex items-center gap-2 z-10">
                        {isProcessing ? (
                          <Loader2 className="w-4 h-4 text-gray-500 animate-spin" />
                        ) : (
                          <Eye className="w-4 h-4 text-gray-500 group-hover/btn:text-white transition-colors" />
                        )}
                        <span className={`text-sm font-medium transition-colors ${
                          isProcessing ? 'text-gray-700' : 'text-gray-700 group-hover/btn:text-white'
                        }`}>
                          {isProcessing
                            ? `Processing... ${progressPercent}%`
                            : isCompleted
                              ? 'Review Protocol'
                              : 'Start Extraction'}
                        </span>
                      </div>
                      <ChevronRight className={`relative w-4 h-4 z-10 transition-colors ${
                        isProcessing ? 'text-gray-400' : 'text-gray-400 group-hover/btn:text-white'
                      }`} />
                    </button>
                  </motion.div>
                );
              })}
            </div>
          ) : (
            <motion.div
              variants={itemVariants}
              className="text-center py-12 text-muted-foreground"
              data-testid="empty-protocols"
            >
              <FileText className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>No protocols have been digitalized yet.</p>
              <p className="text-sm mt-1">Upload a PDF protocol to get started.</p>
            </motion.div>
          )}

          <motion.div
            variants={itemVariants}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={handleFileSelect}
            className={`relative p-8 rounded-2xl border-2 border-dashed transition-all duration-300 cursor-pointer ${
              isDragging
                ? "border-gray-700 bg-gray-100"
                : "border-gray-300 bg-gray-50/50 hover:border-gray-400 hover:bg-gray-100/50"
            }`}
            data-testid="upload-zone"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleFileChange}
              data-testid="input-file-upload"
            />
            <div className="text-center">
              <div className={`w-14 h-14 rounded-full mx-auto mb-4 flex items-center justify-center transition-colors ${
                isDragging ? "bg-gray-300" : "bg-gray-200"
              }`}>
                <Upload className={`w-7 h-7 ${isDragging ? "text-gray-800" : "text-gray-500"}`} />
              </div>
              <h3 className="font-semibold text-foreground mb-2">
                Upload New Protocol
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                Drag and drop a PDF protocol here, or click to browse
              </p>
              <Button
                variant="outline"
                size="sm"
                className="rounded-full"
                data-testid="button-browse-files"
              >
                Browse Files
              </Button>
            </div>
          </motion.div>
        </div>
      </motion.section>

      <motion.section
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8, duration: 0.6 }}
        className="py-16 px-8 border-t border-gray-100"
      >
        <div className="max-w-3xl mx-auto text-center">
          <p className="text-sm text-muted-foreground">
            Powered by advanced language models with domain-specific fine-tuning for clinical research.
          </p>
        </div>
      </motion.section>
    </div>
  );
}
