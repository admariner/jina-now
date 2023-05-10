#!/bin/bash

# Get list of used namespaces from kubectl command
USED_NAMESPACES=$(kubectl get deployment --all-namespaces -l jina.ai/team=now -l jina.ai/jrole=executor -o=jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.finalizers}{"\n"}{end}' | grep kopf | uniq)

ES_HOST=https://$NOW_DEV_CLUSTER_ES_USERNAME:$NOW_DEV_CLUSTER_ES_PASSWORD@${NOW_DEV_CLUSTER_ES_CLUSTER_ENDPOINT}:443
# Get list of indices in Elastic Cloud
INDICES=$(curl -sS -XGET "$ES_HOST/_cat/indices?h=index")
echo $INDICES
# Loop through each index
for INDEX in $INDICES; do
    INDEX_NAMESPACE=$(echo "$INDEX" | cut -d'-' -f2-3)
    echo $INDEX_NAMESPACE
    if ! echo "$USED_NAMESPACES" | grep -q "$INDEX_NAMESPACE"; then
        echo "Deleting index $INDEX"
        curl -XDELETE "$ES_HOST/$INDEX"
    fi
done
