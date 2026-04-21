export type MatterSummary = {
  id: string;
  name: string;
  status: string;
};

export type Citation = {
  documentId: string;
  documentName: string;
  page?: number;
  quote: string;
};
