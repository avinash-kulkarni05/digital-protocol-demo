import usdmData from './usdm-data.json';

export const extractionData = usdmData;

export type ExtractionSection = keyof typeof extractionData.extractionMetadata.qualitySummary;
