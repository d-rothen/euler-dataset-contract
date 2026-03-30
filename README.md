# euler-dataset-contract

Shared dataset-head contract processing for Euler ecosystem packages.

The package owns the cross-package contract layer:

- a `DatasetHeadContract` object
- modality-specific `meta` contracts
- namespaced addon sections such as `euler_train` and `euler_loading`
- contract versioning
- JSON Schema generation for modality metadata

Producer packages like `ds-crawler` should emit the contract. Consumer
packages like `euler-loading` or `euler-train` can parse the shared head
here, inspect namespaces via `get_namespace(...)`, and register their
own namespace validators.
