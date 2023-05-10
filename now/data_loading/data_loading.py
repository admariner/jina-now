import base64
import json
import os
import tempfile
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Type, Union

from docarray import Document, DocumentArray
from docarray.dataclasses import is_multimodal

from now.common.detect_schema import (
    get_first_file_in_folder_structure_s3,
    get_s3_bucket_and_folder_prefix,
)
from now.constants import MAX_DOCS_FOR_BENCHMARKING, MAX_DOCS_FOR_TESTING, DatasetTypes
from now.data_loading.create_dataclass import create_dataclass
from now.data_loading.elasticsearch import ElasticsearchExtractor
from now.executor.preprocessor.s3_download import download_from_bucket
from now.log import yaspin_extended
from now.now_dataclasses import UserInput
from now.utils.common.helpers import flatten_dict, null_context, sigmap
from now.utils.docarray.helpers import get_chunk_by_field_name


def load_data(user_input: UserInput, print_callback=print) -> DocumentArray:
    """Based on the user input, this function will pull the configured DocumentArray dataset ready for the preprocessing
    executor.

    :param user_input: The configured user object. Result from the Jina Now cli dialog.
    :param print_callback: The callback function that should be used to print the status.
    :return: The loaded DocumentArray.
    """
    da = None
    if user_input.dataset_type in [DatasetTypes.DEMO, DatasetTypes.DOCARRAY]:
        user_input.field_names_to_dataclass_fields = {
            field: field for field in user_input.index_fields
        }
        data_class = None
    else:
        data_class, user_input.field_names_to_dataclass_fields = create_dataclass(
            user_input=user_input
        )
    if user_input.dataset_type in [DatasetTypes.DOCARRAY, DatasetTypes.DEMO]:
        print_callback('⬇  Pull DocumentArray dataset')
        da = _pull_docarray(user_input.dataset_name, user_input.admin_name)
        da = _update_fields_and_metadata(da, user_input)
    elif user_input.dataset_type == DatasetTypes.PATH:
        print_callback('💿  Loading files from disk')
        da = _load_from_disk(user_input=user_input, data_class=data_class)
    elif user_input.dataset_type == DatasetTypes.S3_BUCKET:
        print_callback('🗄  Loading files from S3')
        da = list_files_from_s3_bucket(user_input=user_input, data_class=data_class)
    elif user_input.dataset_type == DatasetTypes.ELASTICSEARCH:
        print_callback('🔍  Loading data from Elasticsearch')
        da = _extract_es_data(user_input=user_input, data_class=data_class)
    da = set_modality_da(da)
    _add_metadata_to_chunks(da, user_input)
    if da is None:
        raise ValueError(
            f'Could not load DocumentArray dataset. Please check your configuration: {user_input}.'
        )
    if 'NOW_CI_RUN' in os.environ:
        da = da[:MAX_DOCS_FOR_TESTING]
    elif 'NOW_BENCHMARK_RUN' in os.environ:
        da = da[:MAX_DOCS_FOR_BENCHMARKING]
    return da


def _add_metadata_to_chunks(da, user_input):
    dataclass_fields_to_field_names = {
        v: k for k, v in user_input.field_names_to_dataclass_fields.items()
    }
    for doc in da:
        for dataclass_field, meta_dict in doc._metadata['multi_modal_schema'].items():
            field_name = dataclass_fields_to_field_names.get(dataclass_field, None)
            if 'position' in meta_dict:
                get_chunk_by_field_name(doc, dataclass_field)._metadata[
                    'field_name'
                ] = field_name


def _update_fields_and_metadata(
    da: DocumentArray, user_input: UserInput
) -> DocumentArray:
    """Add selected index fields to da, add the tags, remove non-index chunks,
    and update multi modal schema."""
    if not da:
        return da
    all_fields = da[0]._metadata['multi_modal_schema'].keys()
    for doc in da:
        filtered_chunks = []
        filtered_chunk_names = []
        for field in all_fields:
            field_doc = get_chunk_by_field_name(doc, field)
            if field not in user_input.index_fields:
                if field_doc.blob or field_doc.tensor is not None:
                    continue
                doc.tags.update(
                    {
                        field: field_doc.content
                        if isinstance(field_doc.content, str)
                        else field_doc.uri
                    }
                )
            else:
                filtered_chunks.append(field_doc)
                filtered_chunk_names.append(field)
        doc.chunks = filtered_chunks
        # keep only the index fields in metadata
        doc._metadata['multi_modal_schema'] = {
            field: doc._metadata['multi_modal_schema'][field]
            for field in filtered_chunk_names
        }
        # Update the positions accordingly to access the chunks
        for position, field in enumerate(filtered_chunk_names):
            doc._metadata['multi_modal_schema'][field]['position'] = int(position)

    return da


def _pull_docarray(dataset_name: str, admin_name: str) -> DocumentArray:
    dataset_name = (
        admin_name + '/' + dataset_name if '/' not in dataset_name else dataset_name
    )
    try:
        docs = DocumentArray.pull(
            name=dataset_name, show_progress=True, local_cache=True
        )
        if is_multimodal(docs[0]):
            return docs
        else:
            raise ValueError(
                f'The dataset {dataset_name} does not contain a multimodal DocumentArray. '
                f'Please check documentation https://docarray.jina.ai/fundamentals/dataclass/construct/'
            )
    except Exception:
        raise ValueError(
            'DocumentArray does not exist or you do not have access to it. '
            'Make sure to add user name as a prefix. Check documentation here. '
            'https://docarray.jina.ai/fundamentals/cloud-support/data-management/'
        )


def _extract_es_data(user_input: UserInput, data_class: Type) -> DocumentArray:
    query = {
        'query': {'match_all': {}},
        '_source': True,
    }
    es_extractor = ElasticsearchExtractor(
        query=query,
        index=user_input.es_index_name,
        user_input=user_input,
        data_class=data_class,
        connection_str=user_input.es_host_name,
    )
    extracted_docs = es_extractor.extract()
    return extracted_docs


def _load_from_disk(user_input: UserInput, data_class: Type) -> DocumentArray:
    """
    Loads the data from disk into multimodal documents.

    :param user_input: The user input object.
    :param data_class: The dataclass to use for the DocumentArray.
    """
    dataset_path = user_input.dataset_path.strip()
    dataset_path = os.path.expanduser(dataset_path)
    if os.path.isfile(dataset_path):
        try:
            da = DocumentArray.load_binary(dataset_path)
            if is_multimodal(da[0]):
                da = _update_fields_and_metadata(da, user_input)
                return da
            else:
                raise ValueError(
                    f'The file {dataset_path} does not contain a multimodal DocumentArray.'
                    f'Please check documentation https://docarray.jina.ai/fundamentals/dataclass/construct/'
                )
        except Exception:
            print(f'Failed to load the binary file provided under path {dataset_path}')
            exit(1)
    elif os.path.isdir(dataset_path):
        with yaspin_extended(
            sigmap=sigmap, text="Loading data from folder", color="green"
        ) as spinner:
            spinner.ok('🏭')
            docs = from_files_local(
                dataset_path,
                user_input.index_fields,
                user_input.field_names_to_dataclass_fields,
                data_class,
            )
            return docs
    else:
        raise ValueError(
            f'The provided dataset path {dataset_path} does not'
            f' appear to be a valid file or folder on your system.'
        )


def from_files_local(
    path: str,
    fields: List[str],
    field_names_to_dataclass_fields: Dict,
    data_class: Type,
) -> DocumentArray:
    """Creates a Multi Modal DocumentArray over a list of file path or the content of the files.

    :param path: The path to the directory
    :param fields: The fields to search for in the directory
    :param field_names_to_dataclass_fields: The mapping of the field names to the dataclass fields
    :param data_class: The dataclass to use for the document

    :return: A DocumentArray with the documents
    """

    file_paths = []
    for root, dirs, files in os.walk(path):
        file_paths.extend(
            [os.path.join(root, file) for file in files if not file.startswith('.')]
        )
    folder_generator = os.walk(path, topdown=True)
    current_level = folder_generator.__next__()
    folder_structure = 'sub_folders' if len(current_level[1]) > 0 else 'single_folder'
    if folder_structure == 'sub_folders':
        docs, _ = create_docs_from_subdirectories(
            file_paths, fields, field_names_to_dataclass_fields, data_class
        )
    else:
        docs, _ = create_docs_from_files(
            file_paths, fields, field_names_to_dataclass_fields, data_class
        )
    return DocumentArray(docs)


def create_docs_from_subdirectories(
    file_paths: List,
    fields: List[str],
    field_names_to_dataclass_fields: Dict,
    data_class: Type,
    path: str = None,
    is_s3_dataset: bool = False,
    download_content: bool = False,
    bucket=None,
) -> Tuple[List[Document], Dict[str, dict]]:
    """
    Creates a Multi Modal DocumentArray over a list of subdirectories.

    :param file_paths: The list of file paths
    :param fields: The fields to search for in the directory
    :param field_names_to_dataclass_fields: The mapping of the field names to the dataclass fields
    :param data_class: The dataclass to use for the document
    :param path: The path to the directory
    :param is_s3_dataset: Whether the dataset is stored on s3
    :param download_content: Whether to download the content of the s3 files
    :param bucket: The s3 bucket instance

    :return: The list of documents
    """

    docs = []
    non_json_file_info = []
    json_file_info = []
    folder_files = defaultdict(list)
    folder_files_content = defaultdict(dict)
    # Group the files by the folder they are in
    for file in file_paths:
        path_to_last_folder = (
            '/'.join(file.split('/')[:-1])
            if is_s3_dataset
            else os.sep.join(file.split(os.sep)[:-1])
        )
        folder_files[path_to_last_folder].append(file)

    # Process each files in each folder
    for folder, files in folder_files.items():
        kwargs = {}
        tags_loaded_local = {}
        _s3_uri_for_tags = ''
        file_info = [
            _extract_file_and_full_file_path(file, path, is_s3_dataset)
            for file in files
        ]

        if download_content:
            for file_name, file_full_path in file_info:
                content = get_file_content(bucket, file_full_path, is_s3_dataset)
                folder_files_content[folder.split('/')[-1]][file_name] = content

        for f_name, f_path in file_info:
            if f_name.endswith('.json'):
                json_file_info.append((f_name, f_path))
            else:
                non_json_file_info.append((f_name, f_path))

        # first store index fields given as non json files
        for file, file_full_path in non_json_file_info:
            if file in fields:
                kwargs[field_names_to_dataclass_fields[file]] = file_full_path

        # next check json files that can also contain index fields, and carry on data
        for file, file_full_path in json_file_info:
            if is_s3_dataset:  # s3 data source
                _s3_uri_for_tags = file_full_path
                for field in data_class.__annotations__.keys():
                    if field not in kwargs.keys():
                        kwargs[field] = file_full_path
            else:  # local data source
                with open(file_full_path) as f:
                    json_data = flatten_dict(json.load(f))
                for field, value in json_data.items():
                    if field in fields:
                        kwargs[field_names_to_dataclass_fields[field]] = value
                    else:
                        tags_loaded_local[field] = value
        doc = Document(data_class(**kwargs))
        if _s3_uri_for_tags:
            doc._metadata['_s3_uri_for_tags'] = _s3_uri_for_tags
        elif tags_loaded_local:
            doc.tags.update(tags_loaded_local)
        docs.append(doc)

    return docs, folder_files_content


def create_docs_from_files(
    file_paths: List,
    fields: List[str],
    field_names_to_dataclass_fields: Dict,
    data_class: Type,
    path: str = None,
    is_s3_dataset: bool = False,
    download_content: bool = False,
    bucket=None,
) -> Tuple[List[Document], Dict[str, dict]]:
    """
    Creates a Multi Modal DocumentArray over a list of files.

    :param file_paths: List of file paths
    :param fields: The fields to search for in the directory
    :param field_names_to_dataclass_fields: The mapping of the files to the dataclass fields
    :param data_class: The dataclass to use for the document
    :param path: The path to the directory
    :param is_s3_dataset: Whether the dataset is stored on s3
    :param download_content: Whether to download the content of the files and return as base64 encoded bytes
    :param bucket: The s3 bucket instance

    :return: A list of documents
    """
    docs = []
    folder_content = defaultdict()
    for file in file_paths:
        kwargs = {}
        file, file_full_path = _extract_file_and_full_file_path(
            file, path, is_s3_dataset
        )
        if download_content:
            folder_content[file] = get_file_content(
                bucket, file_full_path, is_s3_dataset
            )
        file_extension = file.split('.')[-1]
        if (
            file_extension == fields[0].split('.')[-1]
        ):  # fields should have only one index field in case of files only
            kwargs[field_names_to_dataclass_fields[fields[0]]] = file_full_path
            docs.append(Document(data_class(**kwargs)))
    return docs, folder_content


def _list_s3_file_paths(bucket, folder_prefix, top_n=None):
    """
    Lists the s3 file paths in an optimized way by finding the best level to use concurrent calls on
    in the file structure, using a threadpool.

    :param bucket: The s3 bucket used
    :param folder_prefix: The root folder prefix

    :return: A list of all s3 paths
    """
    # TODO bucket is not thread safe and outputs duplicate files for different prefixes
    # first_file = get_first_file_in_folder_structure_s3(bucket, folder_prefix)
    # structure_identifier = first_file[len(folder_prefix) :].split('/')
    # folder_structure = (
    #     'sub_folders' if len(structure_identifier) > 1 else 'single_folder'
    # )
    #
    # def get_level_order_prefixes(folder_prefix, level=1):
    #     """
    #     Gets the list of prefixes in a specific level. Levels are defined by the folder structure as follows:
    #     level_1/level_2/.../level_n/file.ext
    #
    #     :param folder_prefix: The current level prefix
    #     :param level: The desired level we want to get to
    #
    #     :return: A list of prefixes
    #     """
    #     level_prefixes = [
    #         obj['Prefix']
    #         for obj in bucket.meta.client.list_objects(
    #             Bucket=bucket.name, Prefix=folder_prefix, Delimiter='/'
    #         )['CommonPrefixes']
    #     ]
    #     if level == 1:
    #         return level_prefixes
    #     else:
    #         prefix_list = []
    #         for prefix in level_prefixes:
    #             prefix_list += get_level_order_prefixes(prefix, level - 1)
    #     return prefix_list
    #
    # def get_prefixes(max_levels=len(structure_identifier) - 2):
    #     """
    #     Finds the best level for the prefixes
    #
    #     :param max_levels: The maximum number of level we can get to, this defaults to len(structure_identifier) - 2
    #     because the latest level (len(structure_identifier) - 1) will only have files, so it won't have any common
    #     prefixes inside.
    #
    #     :return: A list of prefixes
    #     """
    #     level = 1
    #     list_prefixes = get_level_order_prefixes(folder_prefix, level)
    #     prefixes_states = [list_prefixes]
    #     while level < max_levels and len(list_prefixes) < NUM_FOLDERS_THRESHOLD:
    #         level += 1
    #         list_prefixes = get_level_order_prefixes(folder_prefix, level)
    #         prefixes_states.append(list_prefixes)
    #     if len(list_prefixes) > NUM_FOLDERS_THRESHOLD and len(prefixes_states) > 1:
    #         return prefixes_states[-2]
    #     return list_prefixes
    #
    # objects = []
    # if folder_structure == 'sub_folders':
    #     prefixes = get_prefixes()
    #     # TODO: change cpu count to a fixed number
    #     with ThreadPoolExecutor(max_workers=20) as executor:
    #         futures = []
    #         for prefix in prefixes:
    #             pref = ''.join(prefix)
    #             f = executor.submit(
    #                 lambda: list(bucket.objects.filter(Prefix=f'{pref}'))
    #             )
    #             futures.append(f)
    #         for f in futures:
    #             objects += f.result()
    # else:
    #     objects = list(bucket.objects.filter(Prefix=folder_prefix))
    if top_n:
        objects = list(bucket.objects.filter(Prefix=folder_prefix).limit(top_n))
    else:
        objects = list(bucket.objects.filter(Prefix=folder_prefix))
    return [
        obj.key
        for obj in objects
        if not obj.key.endswith('/') and not obj.key.split('/')[-1].startswith('.')
    ]


def validate_shrink_data(file_paths):
    """
    Validates the file paths: Keeps only consistent folders based on the number of files inside them.

    :param file_paths: The initial file paths.

    :return: The file paths to keep.
    """
    dict_fp = defaultdict(int)
    # take the folders of the files
    for file_path in file_paths:
        dict_fp['/'.join(file_path.split('/')[:-1])] += 1

    # remove the keys that don't have the same length as the majority
    val_counts = Counter(dict_fp.values())
    max_occ = max(list(val_counts.values()))
    max_common_element = 0
    for key, value in val_counts.items():
        if value == max_occ:
            max_common_element = max(max_common_element, key)
    keys_to_remove = []
    for key, val in dict_fp.items():
        if val != max_common_element:
            keys_to_remove.append(key)

    # keep only the desired file paths
    files_to_keep = []
    for file_path in file_paths:
        keep = True
        for key in keys_to_remove:
            if file_path.startswith(key):
                keep = False
                break
        if keep:
            files_to_keep.append(file_path)

    return files_to_keep


def get_file_content(bucket, uri, is_s3_uri=True):
    if is_s3_uri:
        with tempfile.TemporaryDirectory() as tmpdir:
            local_file = download_from_bucket(tmpdir, uri, bucket)

            with open(local_file, 'rb') as file:
                content = base64.b64encode(file.read())
    else:
        with open(uri, 'rb') as file:
            content = file.read()

    return content


def list_files_from_s3_bucket(
    user_input: UserInput,
    data_class: Type,
    top_n: int = None,
    verbose=True,
    return_file_content=False,
) -> Union[DocumentArray, Tuple[DocumentArray, Dict[str, dict]]]:
    """
    Loads the data from s3 into multimodal documents. It also supports additional params to return the contents
    of the files.

    :param user_input: The user input object.
    :param data_class: The dataclass to use for the DocumentArray.
    :param top_n: The number of files to pull, if set to None pull all files.
                    top_n is only set when calling from JAC
    :param verbose: If set to True, will print the progress bar.
    :param return_file_content: If set to True, will return all the file content in base64 encoded bytes.

    :return: The DocumentArray with the documents.
    """
    context_manager = yaspin_extended if verbose else null_context
    bucket, folder_prefix = get_s3_bucket_and_folder_prefix(user_input)
    first_file = get_first_file_in_folder_structure_s3(bucket, folder_prefix)
    structure_identifier = first_file[len(folder_prefix) :].split('/')
    folder_structure = (
        'sub_folders' if len(structure_identifier) > 1 else 'single_folder'
    )

    with context_manager(
        sigmap=sigmap, text="Listing files from S3 bucket ...", color="green"
    ) as spinner:
        file_paths = _list_s3_file_paths(bucket, folder_prefix, top_n)
        spinner.ok('🏭')

    if top_n:
        file_paths = validate_shrink_data(file_paths)

    with context_manager(
        sigmap=sigmap, text="Creating docarray from S3 bucket files ...", color="green"
    ) as spinner:
        if folder_structure == 'sub_folders':
            docs, content = create_docs_from_subdirectories(
                file_paths,
                user_input.index_fields,
                user_input.field_names_to_dataclass_fields,
                data_class,
                user_input.dataset_path,
                is_s3_dataset=True,
                bucket=bucket,
                download_content=return_file_content,
            )
        else:
            docs, content = create_docs_from_files(
                file_paths,
                user_input.index_fields,
                user_input.field_names_to_dataclass_fields,
                data_class,
                user_input.dataset_path,
                is_s3_dataset=True,
                bucket=bucket,
                download_content=return_file_content,
            )
        spinner.ok('👝')

    if return_file_content:
        return DocumentArray(docs), content
    return DocumentArray(docs)


def _extract_file_and_full_file_path(file_path, path=None, is_s3_dataset=False):
    """
    Extracts the file name and the full file path from s3 object.

    :param file_path: The file path
    :param path: The path to the directory
    :param is_s3_dataset: Whether the dataset is stored on s3

    :return: The file name and the full file path
    """
    if is_s3_dataset:
        file = file_path.split('/')[-1]
        file_full_path = '/'.join(path.split('/')[:3]) + '/' + file_path
    else:
        file_full_path = file_path
        file = file_path.split(os.sep)[-1]
    return file, file_full_path


def _get_modality(document: Document):
    """
    Detect document's modality based on its `modality` or `mime_type` attributes.

    :param document: The document to detect the modality for.
    """

    modalities = ['text', 'image', 'video']
    if document.modality:
        return document.modality
    mime_type_class = document.mime_type.split('/')[0]
    if document.mime_type == 'application/json':
        return 'text'
    if mime_type_class in modalities:
        return mime_type_class
    document.summary()
    raise ValueError(f'Unknown modality')


def set_modality_da(documents: DocumentArray):
    """
    Set document's modality based on its `modality` or `mime_type` attributes.

    :param documents: The DocumentArray to set the modality for.

    :return: The DocumentArray with the modality set.
    """
    for doc in documents:
        for chunk in doc.chunks:
            chunk.modality = chunk.modality or _get_modality(chunk)
    return documents
