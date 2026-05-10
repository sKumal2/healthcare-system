export interface UserIdentity {
  user_id: string;
  role: "admin" | "clinician" | "patient" | "org_owner";
  jti: string;
  name?: string;
  email?: string;
}

export interface QueryResponse {
  question: string;
  answer: string;
  sources: SourceMetadata[];
  confidence_score: number;
  query_id: string;
  processing_time_ms: number;
  disclaimer: string;
  generated_at: string;
}

export interface SourceMetadata {
  document_id: string;
  title: string;
  source_url?: string;
  author?: string;
  similarity_score: number;
}

export interface Document {
  id: string;
  title: string;
  source_url?: string;
  is_processed: boolean;
  chunks_count: number;
  created_at: string;
  author?: string;
  mime_type?: string;
  file_size_bytes?: number;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    request_id: string;
  };
}
