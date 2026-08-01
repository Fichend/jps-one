import { api } from "@/api/client";

export const huntCopilotApi = {
  start: api.startHuntCopilot,
  sendMessage: api.sendHuntCopilotMessage,
  getSession: api.getHuntCopilotSession,
  listSessions: api.listHuntCopilotSessions,
  duplicateSession: api.duplicateHuntCopilotSession,
  updateStrategy: api.updateHuntCopilotStrategy,
  confirmStrategy: api.confirmHuntCopilotStrategy,
  checkChannels: api.checkHuntCopilotChannels,
  execute: api.executeHuntCopilot,
  listSkills: api.listHuntCopilotSkills,
  listToolStatus: api.listSearchToolStatus,
  listToolCapabilities: api.listSearchToolCapabilities,
};
