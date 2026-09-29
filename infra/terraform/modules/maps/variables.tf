variable "resource_group_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "name" {
  type = string
}

variable "reader_principal_ids" {
  type    = map(string)
  default = {}
}
