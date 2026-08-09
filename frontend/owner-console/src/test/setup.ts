import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { ownerApiServer } from "../api/server";

beforeAll(() => ownerApiServer.listen({ onUnhandledRequest: "error" }));
afterEach(() => ownerApiServer.resetHandlers());
afterAll(() => ownerApiServer.close());
