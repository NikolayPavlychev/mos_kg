# Organization Source Mapping

Supported source fields for normalization into graph ontology:

- `id`, `global_id`, `uid` -> `Organization.id`
- `name`, `organization_name`, `org_name`, `title` -> `Organization.name` / `Place.name`
- `category`, `type`, `rubric` -> `Category.name`
- `city` -> `City.name` (default `Москва`)
- `district`, `adm_area`, `area`, `rayon` -> `District.name`
- `address`, `full_address`, `location` -> `Address.full_address`
- `lat`, `latitude`, `geo_lat` -> `Address.lat`
- `lon`, `longitude`, `geo_lon` -> `Address.lon`

Rows without organization name are skipped.
