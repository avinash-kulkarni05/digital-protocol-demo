export interface SiteLogisticsCompliance {
  hasExperiencedPI: boolean;
  hasTrainedStaff: boolean;
  hasCertifiedLab: boolean;
  hasIRBApproval: boolean;
  hasPharmacyCapability: boolean;
}

export interface Site {
  siteId: string;
  siteName: string;
  systemId: string;
  systemName: string;
  city: string;
  state: string;
  stateCode: string;
  lat: number;
  lng: number;
  totalPatients: number;
  stageEligibility: Record<string, number>;
  logistics?: SiteLogisticsCompliance;
  hasCompetingNSCLCTrial?: boolean;
}

export interface HealthcareSystem {
  systemId: string;
  systemName: string;
  sites: Site[];
}

export const healthcareSystems: HealthcareSystem[] = [
  {
    systemId: "sys_ascension",
    systemName: "Ascension Cancer Care Center",
    sites: [
      {
        siteId: "site_asc_001",
        siteName: "Ascension St Vincent's Riverside Mary Virginia Terry Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Jacksonville",
        state: "Florida",
        stateCode: "FL",
        lat: 30.3157,
        lng: -81.6742,
        totalPatients: 11250,
        stageEligibility: {
          "FS_1": 8100,
          "FS_2": 5200,
          "FS_3": 4800,
          "FS_4": 3100,
          "FS_5": 2400,
          "FS_6": 1850
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_002",
        siteName: "Ascension Via Christi Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Wichita",
        state: "Kansas",
        stateCode: "KS",
        lat: 37.6872,
        lng: -97.3301,
        totalPatients: 8920,
        stageEligibility: {
          "FS_1": 4200,
          "FS_2": 6800,
          "FS_3": 5900,
          "FS_4": 5200,
          "FS_5": 4100,
          "FS_6": 3600
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: false,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_003",
        siteName: "Ascension Saint Thomas Midtown Hospital Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Nashville",
        state: "Tennessee",
        stateCode: "TN",
        lat: 36.1526,
        lng: -86.7957,
        totalPatients: 14280,
        stageEligibility: {
          "FS_1": 9520,
          "FS_2": 7800,
          "FS_3": 4200,
          "FS_4": 3800,
          "FS_5": 3200,
          "FS_6": 2100
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: true
      },
      {
        siteId: "site_asc_004",
        siteName: "Ascension Saint Agnes Cancer Institute",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Baltimore",
        state: "Maryland",
        stateCode: "MD",
        lat: 39.2805,
        lng: -76.6706,
        totalPatients: 10650,
        stageEligibility: {
          "FS_1": 5200,
          "FS_2": 4800,
          "FS_3": 7200,
          "FS_4": 6100,
          "FS_5": 5400,
          "FS_6": 4800
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: false,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_005",
        siteName: "Ascension NE Wisconsin St Elizabeth Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Appleton",
        state: "Wisconsin",
        stateCode: "WI",
        lat: 44.2619,
        lng: -88.4154,
        totalPatients: 7840,
        stageEligibility: {
          "FS_1": 3800,
          "FS_2": 3200,
          "FS_3": 5600,
          "FS_4": 5100,
          "FS_5": 4800,
          "FS_6": 4200
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: false
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_006",
        siteName: "Ascension St Vincent Kokomo Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Kokomo",
        state: "Indiana",
        stateCode: "IN",
        lat: 40.4864,
        lng: -86.1336,
        totalPatients: 6520,
        stageEligibility: {
          "FS_1": 2800,
          "FS_2": 2400,
          "FS_3": 2100,
          "FS_4": 4800,
          "FS_5": 4200,
          "FS_6": 3900
        },
        logistics: {
          hasExperiencedPI: false,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_007",
        siteName: "Ascension Seton Cancer Survivor Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Austin",
        state: "Texas",
        stateCode: "TX",
        lat: 30.3074,
        lng: -97.7463,
        totalPatients: 15680,
        stageEligibility: {
          "FS_1": 12400,
          "FS_2": 9800,
          "FS_3": 6200,
          "FS_4": 4100,
          "FS_5": 2800,
          "FS_6": 1900
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: true
      },
      {
        siteId: "site_asc_008",
        siteName: "Ascension St Vincent Anderson Regional Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Anderson",
        state: "Indiana",
        stateCode: "IN",
        lat: 40.1053,
        lng: -85.6803,
        totalPatients: 5890,
        stageEligibility: {
          "FS_1": 2100,
          "FS_2": 1800,
          "FS_3": 1600,
          "FS_4": 3200,
          "FS_5": 4100,
          "FS_6": 3800
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: false,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_009",
        siteName: "Ascension NE Wisconsin Mercy Campus Wachtel Cancer Center",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Oshkosh",
        state: "Wisconsin",
        stateCode: "WI",
        lat: 44.0247,
        lng: -88.5426,
        totalPatients: 6340,
        stageEligibility: {
          "FS_1": 2400,
          "FS_2": 2100,
          "FS_3": 4800,
          "FS_4": 4200,
          "FS_5": 5100,
          "FS_6": 4600
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: true,
          hasCertifiedLab: true,
          hasIRBApproval: true,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: false
      },
      {
        siteId: "site_asc_010",
        siteName: "Women's Comprehensive Cancer Center at Ascension Saint Thomas",
        systemId: "sys_ascension",
        systemName: "Ascension Cancer Care Center",
        city: "Nashville",
        state: "Tennessee",
        stateCode: "TN",
        lat: 36.1498,
        lng: -86.7989,
        totalPatients: 9120,
        stageEligibility: {
          "FS_1": 4800,
          "FS_2": 6200,
          "FS_3": 5400,
          "FS_4": 7100,
          "FS_5": 6400,
          "FS_6": 5200
        },
        logistics: {
          hasExperiencedPI: true,
          hasTrainedStaff: false,
          hasCertifiedLab: true,
          hasIRBApproval: false,
          hasPharmacyCapability: true
        },
        hasCompetingNSCLCTrial: true
      }
    ]
  },
  {
    systemId: "sys_hca",
    systemName: "HCA Healthcare",
    sites: [
      {
        siteId: "site_hca_001",
        siteName: "HCA Houston Medical Center",
        systemId: "sys_hca",
        systemName: "HCA Healthcare",
        city: "Houston",
        state: "Texas",
        stateCode: "TX",
        lat: 29.7604,
        lng: -95.3698,
        totalPatients: 18920,
        stageEligibility: {
          "STAGE_INC_1": 12650,
          "STAGE_INC_2": 9340,
          "STAGE_EXC_1": 7890,
          "STAGE_FINAL": 5120
        }
      },
      {
        siteId: "site_hca_002",
        siteName: "HCA TriStar Nashville",
        systemId: "sys_hca",
        systemName: "HCA Healthcare",
        city: "Nashville",
        state: "Tennessee",
        stateCode: "TN",
        lat: 36.1627,
        lng: -86.7816,
        totalPatients: 14560,
        stageEligibility: {
          "STAGE_INC_1": 9780,
          "STAGE_INC_2": 7230,
          "STAGE_EXC_1": 6120,
          "STAGE_FINAL": 4010
        }
      },
      {
        siteId: "site_hca_003",
        siteName: "HCA Sunrise Las Vegas",
        systemId: "sys_hca",
        systemName: "HCA Healthcare",
        city: "Las Vegas",
        state: "Nevada",
        stateCode: "NV",
        lat: 36.1699,
        lng: -115.1398,
        totalPatients: 11230,
        stageEligibility: {
          "STAGE_INC_1": 7540,
          "STAGE_INC_2": 5620,
          "STAGE_EXC_1": 4780,
          "STAGE_FINAL": 3120
        }
      },
      {
        siteId: "site_hca_004",
        siteName: "HCA Mountain View Denver",
        systemId: "sys_hca",
        systemName: "HCA Healthcare",
        city: "Denver",
        state: "Colorado",
        stateCode: "CO",
        lat: 39.7392,
        lng: -104.9903,
        totalPatients: 10890,
        stageEligibility: {
          "STAGE_INC_1": 7280,
          "STAGE_INC_2": 5430,
          "STAGE_EXC_1": 4620,
          "STAGE_FINAL": 3010
        }
      }
    ]
  },
  {
    systemId: "sys_kaiser",
    systemName: "Kaiser Permanente",
    sites: [
      {
        siteId: "site_kai_001",
        siteName: "Kaiser Los Angeles Medical Center",
        systemId: "sys_kaiser",
        systemName: "Kaiser Permanente",
        city: "Los Angeles",
        state: "California",
        stateCode: "CA",
        lat: 34.0522,
        lng: -118.2437,
        totalPatients: 22340,
        stageEligibility: {
          "STAGE_INC_1": 14890,
          "STAGE_INC_2": 11230,
          "STAGE_EXC_1": 9540,
          "STAGE_FINAL": 6230
        }
      },
      {
        siteId: "site_kai_002",
        siteName: "Kaiser San Francisco",
        systemId: "sys_kaiser",
        systemName: "Kaiser Permanente",
        city: "San Francisco",
        state: "California",
        stateCode: "CA",
        lat: 37.7749,
        lng: -122.4194,
        totalPatients: 16780,
        stageEligibility: {
          "STAGE_INC_1": 11230,
          "STAGE_INC_2": 8450,
          "STAGE_EXC_1": 7180,
          "STAGE_FINAL": 4680
        }
      },
      {
        siteId: "site_kai_003",
        siteName: "Kaiser Portland",
        systemId: "sys_kaiser",
        systemName: "Kaiser Permanente",
        city: "Portland",
        state: "Oregon",
        stateCode: "OR",
        lat: 45.5152,
        lng: -122.6784,
        totalPatients: 12450,
        stageEligibility: {
          "STAGE_INC_1": 8340,
          "STAGE_INC_2": 6280,
          "STAGE_EXC_1": 5340,
          "STAGE_FINAL": 3480
        }
      },
      {
        siteId: "site_kai_004",
        siteName: "Kaiser Seattle",
        systemId: "sys_kaiser",
        systemName: "Kaiser Permanente",
        city: "Seattle",
        state: "Washington",
        stateCode: "WA",
        lat: 47.6062,
        lng: -122.3321,
        totalPatients: 14230,
        stageEligibility: {
          "STAGE_INC_1": 9540,
          "STAGE_INC_2": 7180,
          "STAGE_EXC_1": 6120,
          "STAGE_FINAL": 3980
        }
      }
    ]
  },
  {
    systemId: "sys_commonspirit",
    systemName: "CommonSpirit Health",
    sites: [
      {
        siteId: "site_com_001",
        siteName: "CommonSpirit Phoenix",
        systemId: "sys_commonspirit",
        systemName: "CommonSpirit Health",
        city: "Phoenix",
        state: "Arizona",
        stateCode: "AZ",
        lat: 33.4484,
        lng: -112.0740,
        totalPatients: 13560,
        stageEligibility: {
          "STAGE_INC_1": 9080,
          "STAGE_INC_2": 6840,
          "STAGE_EXC_1": 5820,
          "STAGE_FINAL": 3790
        }
      },
      {
        siteId: "site_com_002",
        siteName: "CommonSpirit Omaha",
        systemId: "sys_commonspirit",
        systemName: "CommonSpirit Health",
        city: "Omaha",
        state: "Nebraska",
        stateCode: "NE",
        lat: 41.2565,
        lng: -95.9345,
        totalPatients: 8920,
        stageEligibility: {
          "STAGE_INC_1": 5980,
          "STAGE_INC_2": 4510,
          "STAGE_EXC_1": 3840,
          "STAGE_FINAL": 2500
        }
      },
      {
        siteId: "site_com_003",
        siteName: "CommonSpirit Little Rock",
        systemId: "sys_commonspirit",
        systemName: "CommonSpirit Health",
        city: "Little Rock",
        state: "Arkansas",
        stateCode: "AR",
        lat: 34.7465,
        lng: -92.2896,
        totalPatients: 7680,
        stageEligibility: {
          "STAGE_INC_1": 5140,
          "STAGE_INC_2": 3870,
          "STAGE_EXC_1": 3290,
          "STAGE_FINAL": 2140
        }
      }
    ]
  },
  {
    systemId: "sys_mayo",
    systemName: "Mayo Clinic Health System",
    sites: [
      {
        siteId: "site_may_001",
        siteName: "Mayo Clinic Rochester",
        systemId: "sys_mayo",
        systemName: "Mayo Clinic Health System",
        city: "Rochester",
        state: "Minnesota",
        stateCode: "MN",
        lat: 44.0121,
        lng: -92.4802,
        totalPatients: 24560,
        stageEligibility: {
          "STAGE_INC_1": 16420,
          "STAGE_INC_2": 12380,
          "STAGE_EXC_1": 10540,
          "STAGE_FINAL": 6860
        }
      },
      {
        siteId: "site_may_002",
        siteName: "Mayo Clinic Jacksonville",
        systemId: "sys_mayo",
        systemName: "Mayo Clinic Health System",
        city: "Jacksonville",
        state: "Florida",
        stateCode: "FL",
        lat: 30.3322,
        lng: -81.6557,
        totalPatients: 16890,
        stageEligibility: {
          "STAGE_INC_1": 11310,
          "STAGE_INC_2": 8520,
          "STAGE_EXC_1": 7250,
          "STAGE_FINAL": 4720
        }
      },
      {
        siteId: "site_may_003",
        siteName: "Mayo Clinic Scottsdale",
        systemId: "sys_mayo",
        systemName: "Mayo Clinic Health System",
        city: "Scottsdale",
        state: "Arizona",
        stateCode: "AZ",
        lat: 33.4942,
        lng: -111.9261,
        totalPatients: 14230,
        stageEligibility: {
          "STAGE_INC_1": 9530,
          "STAGE_INC_2": 7180,
          "STAGE_EXC_1": 6110,
          "STAGE_FINAL": 3980
        }
      }
    ]
  },
  {
    systemId: "sys_cleveland",
    systemName: "Cleveland Clinic",
    sites: [
      {
        siteId: "site_cle_001",
        siteName: "Cleveland Clinic Main Campus",
        systemId: "sys_cleveland",
        systemName: "Cleveland Clinic",
        city: "Cleveland",
        state: "Ohio",
        stateCode: "OH",
        lat: 41.5034,
        lng: -81.6214,
        totalPatients: 21340,
        stageEligibility: {
          "STAGE_INC_1": 14280,
          "STAGE_INC_2": 10760,
          "STAGE_EXC_1": 9160,
          "STAGE_FINAL": 5960
        }
      },
      {
        siteId: "site_cle_002",
        siteName: "Cleveland Clinic Florida",
        systemId: "sys_cleveland",
        systemName: "Cleveland Clinic",
        city: "Weston",
        state: "Florida",
        stateCode: "FL",
        lat: 26.1003,
        lng: -80.3998,
        totalPatients: 11560,
        stageEligibility: {
          "STAGE_INC_1": 7740,
          "STAGE_INC_2": 5830,
          "STAGE_EXC_1": 4960,
          "STAGE_FINAL": 3230
        }
      },
      {
        siteId: "site_cle_003",
        siteName: "Cleveland Clinic Abu Dhabi",
        systemId: "sys_cleveland",
        systemName: "Cleveland Clinic",
        city: "Abu Dhabi",
        state: "UAE",
        stateCode: "AE",
        lat: 24.4539,
        lng: 54.3773,
        totalPatients: 8920,
        stageEligibility: {
          "STAGE_INC_1": 5970,
          "STAGE_INC_2": 4500,
          "STAGE_EXC_1": 3830,
          "STAGE_FINAL": 2490
        }
      }
    ]
  }
];

export const getAllSites = (): Site[] => {
  return healthcareSystems.flatMap(system => system.sites);
};

export const getUSSites = (): Site[] => {
  const usCodes = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"];
  return getAllSites().filter(site => usCodes.includes(site.stateCode));
};

export interface CriteriaContext {
  stageId: string;
  totalCriteria: number;
  selectedCriteria: number;
}

export const calculateEligiblePatients = (
  site: Site, 
  stageIds: string[], 
  criteriaContext?: CriteriaContext[]
): number => {
  if (stageIds.length === 0) return site.totalPatients;
  
  let eligible = site.totalPatients;
  for (const stageId of stageIds) {
    const stageEligible = site.stageEligibility[stageId];
    if (stageEligible !== undefined) {
      let retentionRate = stageEligible / site.totalPatients;
      
      // Adjust retention rate based on how many criteria are selected in this stage
      if (criteriaContext) {
        const ctx = criteriaContext.find(c => c.stageId === stageId);
        if (ctx && ctx.totalCriteria > 0) {
          const criteriaRatio = ctx.selectedCriteria / ctx.totalCriteria;
          // Interpolate: 0 criteria = 100% retention, all criteria = full stage retention
          retentionRate = 1 - (1 - retentionRate) * criteriaRatio;
        }
      }
      
      eligible = Math.floor(eligible * retentionRate);
    } else {
      eligible = Math.floor(eligible * 0.65);
    }
  }
  return Math.max(eligible, 0);
};

export const sortSitesByEligibility = (
  sites: Site[], 
  stageIds: string[],
  criteriaContext?: CriteriaContext[]
): Site[] => {
  return [...sites].sort((a, b) => {
    const eligibleA = calculateEligiblePatients(a, stageIds, criteriaContext);
    const eligibleB = calculateEligiblePatients(b, stageIds, criteriaContext);
    return eligibleB - eligibleA;
  });
};
