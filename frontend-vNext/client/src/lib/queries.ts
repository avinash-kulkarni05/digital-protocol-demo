import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export const STUDY_ID = "M14-031";

export function useDocument(studyId: string = STUDY_ID, options?: { refetchInterval?: number | false }) {
  return useQuery({
    queryKey: ["document", studyId],
    queryFn: () => api.documents.getByStudyId(studyId),
    retry: 1,
    // Auto-refetch to pick up extraction updates (SOA, main pipeline, etc.)
    refetchInterval: options?.refetchInterval ?? 15000, // Default: refetch every 15 seconds
    refetchIntervalInBackground: false, // Don't refetch when tab is not active
  });
}

export function useAllDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => api.documents.getAll(),
  });
}

/**
 * Hook to update a field in the USDM document with audit logging.
 * Provides optimistic updates for responsive UI.
 */
export function useFieldUpdate(
  documentId: number,
  studyId: string,
  studyTitle: string,
  updatedBy: string = "anonymous"
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ path, value }: { path: string; value: any }) =>
      api.documents.updateField(documentId, {
        path,
        value,
        studyId,
        studyTitle,
        updatedBy,
      }),

    // Optimistic update - update the cache immediately before the API call completes
    onMutate: async ({ path, value }) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["document", studyId] });

      // Snapshot the previous value
      const previousDocument = queryClient.getQueryData(["document", studyId]);

      // Optimistically update the cache
      if (previousDocument) {
        queryClient.setQueryData(["document", studyId], (old: any) => {
          if (!old) return old;
          const newData = JSON.parse(JSON.stringify(old)); // Deep clone

          // Navigate to the field and update it
          const pathParts = path.split(".");
          let current = newData.usdmData;
          for (let i = 0; i < pathParts.length - 1; i++) {
            if (current && typeof current === "object") {
              current = current[pathParts[i]];
            }
          }
          if (current && typeof current === "object") {
            current[pathParts[pathParts.length - 1]] = value;
          }

          return newData;
        });
      }

      return { previousDocument };
    },

    // If the mutation fails, roll back to the previous value
    onError: (err, variables, context) => {
      if (context?.previousDocument) {
        queryClient.setQueryData(["document", studyId], context.previousDocument);
      }
      console.error("Failed to update field:", err);
    },

    // Always refetch after error or success
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["document", studyId] });
      queryClient.invalidateQueries({ queryKey: ["edit-history", documentId] });
    },
  });
}

/**
 * Hook to fetch the edit history for a document.
 */
export function useEditHistory(documentId: number | undefined) {
  return useQuery({
    queryKey: ["edit-history", documentId],
    queryFn: () => api.documents.getEditHistory(documentId!),
    enabled: !!documentId,
  });
}
