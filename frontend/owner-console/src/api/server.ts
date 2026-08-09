import { setupServer } from "msw/node";
import { ownerApiHandlers } from "./handlers";

export const ownerApiServer = setupServer(...ownerApiHandlers);
