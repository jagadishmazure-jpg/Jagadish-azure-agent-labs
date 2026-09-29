locals {
  profiles = {
    "cost-min" = { log_quota_gb = 1, capacity = 10 }
    standard   = { log_quota_gb = -1, capacity = 30 }
  }
  p = local.profiles[var.cost_profile]
  n = module.naming.prefix_for

  tags = merge({
    env           = var.environment
    owner         = var.owner
    project       = var.project
    "cost-center" = var.cost_center
    lab           = "disaster-signal-fusion"
    "data-zone"   = var.data_zone
    "managed-by"  = "terraform"
  }, var.extra_tags)
}
