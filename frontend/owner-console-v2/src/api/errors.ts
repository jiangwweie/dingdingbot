interface ErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
  };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function apiErrorFromResponse(response: Response, payload: unknown): ApiError {
  const envelope = payload as ErrorEnvelope | null;
  const code =
    typeof envelope?.error?.code === "string" ? envelope.error.code : "request_failed";
  const message =
    typeof envelope?.error?.message === "string"
      ? envelope.error.message
      : "Request failed";

  return new ApiError(response.status, code, message);
}

export function isUnauthorized(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 401;
}
