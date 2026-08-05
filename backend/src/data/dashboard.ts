export const dashboardData = {
  insights: [
    {
      id: "campaign",
      label: "Campaign Insights",
      description: "Live program performance.",
      accent: "#FF4F00",
      icon: "megaphone",
      metrics: [
        { label: "Active Campaigns", value: "5", sub: "▲ 1 scheduled" },
        { label: "Engagement Rate", value: "57%" },
        { label: "Pending Approval", value: "9", sub: "2 urgent" },
      ],
      sparkline: [2, 3, 3, 4, 4, 5, 5],
    },
    {
      id: "hcp",
      label: "HCP Insights",
      description: "Reach across the database.",
      accent: "#3B82F6",
      icon: "stethoscope",
      metrics: [
        { label: "Total HCPs Reached", value: "15125" },
        { label: "Engagement Rate", value: "57%" },
        { label: "New Audience", value: "1493" },
      ],
      sparkline: [8, 9, 10, 12, 13, 14, 15],
    },
    {
      id: "field-rep",
      label: "Field Rep Insights",
      description: "Sales rep activity & gamification.",
      accent: "#10B981",
      icon: "trophy",
      metrics: [
        { label: "Total Reps Reached", value: "192" },
        { label: "Engagement Rate", value: "57%" },
        { label: "MR Submissions", value: "2838" },
      ],
      sparkline: [5, 6, 6, 7, 7, 8, 8],
    },
    {
      id: "agentic-iq",
      label: "Agentic IQ",
      description: "Autonomous control plane.",
      accent: "#8B5CF6",
      icon: "brain",
      metrics: [
        { label: "Manhours Saved", value: "58.6h" },
        { label: "Active Agents", value: "7" },
        { label: "Actions Executed", value: "493" },
      ],
      sparkline: [1, 1, 2, 3, 4, 6, 9],
    },
  ],
  activeCampaigns: [
    {
      name: "Oflox OZ Patient Education Push",
      segment: "Cardiology · Specialists",
      percent: 72,
      status: "Paused",
    },
    {
      name: "Antiflu Clinical Update Q4",
      segment: "Cardiology · Specialists",
      percent: 48,
      status: "Optimizing",
    },
    {
      name: "Nicotex Clinical Update Q1",
      segment: "Cardiology · GPs",
      percent: 70,
      status: "Optimizing",
    },
    {
      name: "Maxiflo Clinical Update Q4",
      segment: "Diabetology & Metabolic Disorders · HCPs",
      percent: 77,
      status: "Paused",
    },
  ],
  campaignPerformance: [
    { channel: "WhatsApp", sent: 6299, delivered: 96, opened: 48, clicked: 12 },
    { channel: "SMS", sent: 3747, delivered: 96, opened: 41, clicked: 12 },
    { channel: "Email", sent: 9107, delivered: 92, opened: 51, clicked: 15 },
  ],
  topContent: [
    { title: "Patient Counselling Tips for Physicians", views: 4298 },
    { title: "Adverse Event Profile for Oncologists", views: 3536 },
    { title: "Mechanism of Action for Physicians", views: 3075 },
    { title: "Dosing Guide for Physicians", views: 2739 },
    { title: "Adverse Event Profile for Physicians", views: 1958 },
  ],
};
