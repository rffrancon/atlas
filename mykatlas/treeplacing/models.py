from __future__ import print_function
import json
import sys
import os
import logging
import operator
from os import path
from ga4ghmongo.schema import Variant
from ga4ghmongo.schema import VariantSet
from ga4ghmongo.schema import VariantCall
from ga4ghmongo.schema import VariantCallSet
from mykatlas.utils import lazyprop
sys.path.append(path.abspath("../"))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Placer(object):

    """Placer"""

    def __init__(self, root = None):
        super(Placer, self).__init__()
        self.root = root

    def walker(self, sample, verbose=False):
        logger.debug("Placing sample %s on the tree" % sample)
        variant_calls = VariantCall.objects(
            call_set=VariantCallSet.objects.get(
                sample_id=sample))
        logger.debug("Using %i variant calls" % len(variant_calls))
        return self.root.search(variant_calls=variant_calls)

    def _query_call_sets_for_distinct_variants(self):
        return VariantCall._get_collection().aggregate([
            {"$match": {
                }
            },
            {"$group": {
                "_id": {"call_set": "$call_set"},
                "variants" : {"$addToSet" : "$variant"}
                }
            }
        ])   

    def _parse_distinct_variant_query(self, variant_call_sets):
        call_set_to_distinct_variants = {}
        for vc in variant_call_sets:
            ## Update dict
            call_set_id = str(vc.get("_id").get("call_set"))
            variant_id_list = [str(v) for v in vc.get("variants")]
            call_set_to_distinct_variants[call_set_id] = variant_id_list
        return call_set_to_distinct_variants

    def _print_top_10_matches(self, sample_to_distance_metrics):
        sorted_sample_to_distance_metrics = sorted(sample_to_distance_metrics.items(), key=operator.itemgetter(1))
        for i in range(10):
            print (i+1, sorted_sample_to_distance_metrics[i][0],sorted_sample_to_distance_metrics[i][1])

    def _load_call_set_to_distinct_variants_from_cache(self):
        logger.info("Loading distinct_variants query from cache")
        with open("/tmp/call_set_to_distinct_variants_cache.json", 'r') as infile:
            return json.load(infile)     

    def _dump_call_set_to_distinct_variants_to_cache(self, call_set_to_distinct_variants):
        with open("/tmp/call_set_to_distinct_variants_cache.json", 'w') as outfile:
            json.dump(call_set_to_distinct_variants, outfile)   

    def _calculate_call_set_to_distinct_variants(self):
        logger.info("Running distinct_variants query in DB")        
        variant_call_sets = self._query_call_sets_for_distinct_variants()
        call_set_to_distinct_variants = self._parse_distinct_variant_query(variant_call_sets)
        self._dump_call_set_to_distinct_variants_to_cache(call_set_to_distinct_variants)        
        return call_set_to_distinct_variants

    def _get_call_set_to_distinct_variants(self, use_cache):
        if use_cache:
            try:
                call_set_to_distinct_variants = self._load_call_set_to_distinct_variants_from_cache()
            except (IOError, ValueError):
                call_set_to_distinct_variants = self._calculate_call_set_to_distinct_variants()
        else:
            call_set_to_distinct_variants = self._calculate_call_set_to_distinct_variants()        
        return call_set_to_distinct_variants

    def exhaustive_overlap(self, query_sample, use_cache=True):
        query_sample_call_set=VariantCallSet.objects.get(sample_id=query_sample)
        call_set_to_distinct_variants = self._get_call_set_to_distinct_variants(use_cache)
        best_sample_symmetric_difference_count = 10000
        best_sample = None
        best_intersect = 0
        sample_to_distance_metrics = {}
        sample_variants_set = set([str(v.id) for v in VariantCall.objects(call_set = query_sample_call_set).distinct("variant")])
        logger.info("calculating distinct metrics againsts all %i samples" % len(call_set_to_distinct_variants))
        for call_set_id, variant_id_list in call_set_to_distinct_variants.items():
            ## Check similarity
            sample = VariantCallSet.objects.get(id = call_set_id).sample_id            
            current_sample_variant_set= set(variant_id_list)            
            intersection_count = len(current_sample_variant_set & sample_variants_set)
            symmetric_difference_count = len(current_sample_variant_set ^ sample_variants_set)
            if call_set_id != str(query_sample_call_set.id):
                sample_to_distance_metrics[sample] = symmetric_difference_count
                if symmetric_difference_count < best_sample_symmetric_difference_count :
                    best_sample_symmetric_difference_count = symmetric_difference_count
                    best_sample = sample
                    best_intersect = intersection_count


        logger.info("Finished searching %i samples - closest sample is %s with %i overlapping variants and %i variants between them" % (len(call_set_to_distinct_variants),best_sample, best_intersect, best_sample_symmetric_difference_count))
        self._print_top_10_matches(sample_to_distance_metrics)
        return best_sample 

    def place(self, sample, use_cache = True):     
        return self.exhaustive_overlap(sample, use_cache = use_cache)

# class Tree(dict):
#     """Tree is defined by a dict of nodes"""
#     def __init__(self):
#         super(Tree, self).__init__()


def lazyprop(fn):
    attr_name = '_lazy_' + fn.__name__

    @property
    def _lazyprop(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)
    return _lazyprop


class Node(object):

    """docstring for Node"""

    def __init__(self, children=[]):
        super(Node, self).__init__()
        self.parent = None
        self.children = children  # List of nodes
        for child in self.children:
            child.add_parent(self)
        self._phylo_snps = None

    def add_parent(self, parent):
        self.parent = parent

    def other_child(self, node):
        for child in self.children:
            if child != node:
                return child

    @property
    def samples(self):
        samples = []
        for child in self.children:
            samples.extend(child.samples)
        return samples  # List of sample below node in tree

    def __str__(self):
        return "Node with children %s " % ",".join(self.samples)

    def __repr__(self):
        return "Node with children %s " % ",".join(self.samples)

    @property
    def num_samples(self):
        return len(self.samples)

    @property
    def is_leaf(self):
        return False

    @property
    def is_node(self):
        return True

    @property
    def in_group_call_sets(self):
        return VariantCallSet.objects(sample_id__in=self.samples)

    def count_number_of_ingroup_call_sets(self):
        return float(self.in_group_call_sets.count())

    @property
    def outgroup_call_set(self):
        if self.parent:
            return VariantCallSet.objects(
                sample_id__in=self.parent.other_child(self).samples)
        else:
            return []

    def count_number_of_outgroup_call_sets(self):
        if self.outgroup_call_set:
            return float(self.outgroup_call_set.count())
        else:
            return 0

    def query_variant_count(self, call_sets):
        variant_calls = VariantCall._get_collection().aggregate([
            {"$match": {
                "call_set": {"$in": [cs.id for cs in call_sets]}
            }
            },
            {"$group": {
                "_id": {"variant": "$variant"},
                "count": {"$sum": 1}
            }
            },
            {"$match": {
                "count": {"$gt": 0}
            }
            }
        ])
        counts = {}
        for res in variant_calls:
            counts[str(res.get("_id", {}).get("variant"))
                   ] = res.get("count", 0)
        return counts

    def calculate_phylo_snps(self):
        logger.debug("calculating phylo_snps for %s" % self)
        out_dict = {}
        number_of_ingroup_samples = self.count_number_of_ingroup_call_sets()
        logger.debug("Ingroup call sets %i" % number_of_ingroup_samples)
        number_of_outgroup_samples = self.count_number_of_outgroup_call_sets()
        logger.debug("Outgroup call sets %i" % number_of_outgroup_samples)

        logging.debug("Querying for in_group_variant_calls_counts")
        in_group_variant_calls_counts = self.query_variant_count(
            self.in_group_call_sets)
        logging.debug("Querying for out_group_variant_calls_counts")
        out_group_variant_calls_counts = self.query_variant_count(
            self.outgroup_call_set)

        for variant, count_ingroup in in_group_variant_calls_counts.items():
            ingroup_freq = float(count_ingroup) / number_of_ingroup_samples
            if number_of_outgroup_samples != 0:
                count_outgroup = out_group_variant_calls_counts.get(variant, 0)
                outgroup_freq = float(
                    count_outgroup) / number_of_outgroup_samples
            else:
                count_outgroup = 0
                outgroup_freq = 0
            # logging.debug(
            #     "%s has ingroup count %i freq %f.  outgroup count %i freq %f. Diff %f" %
            #     (variant,
            #      count_ingroup,
            #      ingroup_freq,
            #      count_outgroup,
            #      outgroup_freq,
            #      ingroup_freq -
            #      outgroup_freq))
            out_dict[variant] = ingroup_freq - outgroup_freq
        self._phylo_snps = out_dict
        return self._phylo_snps

    @lazyprop
    def phylo_snps(self):
        return self.calculate_phylo_snps()

    def search(self, variant_calls):
        assert self.children[0].parent is not None
        assert self.children[1].parent is not None
        logger.info(
            "step %s %s %s " %
            (self, self.children[0], self.children[1]))

        overlap = []
        # Get the overlapping SNPS
        variant_set = set([str(vc.variant.id) for vc in variant_calls])

        l0 = list(set(self.children[0].phylo_snps.keys()) & variant_set)
        l1 = list(set(self.children[1].phylo_snps.keys()) & variant_set)
        logger.info("left %i right %i " % (len(l0), len(l1)))
        count0 = 0
        count1 = 0
        for k in l0:
            count0 += self.children[0].phylo_snps[k]
        for k in l1:
            count1 += self.children[1].phylo_snps[k]
        overlap = (count0, count1)
        logger.info(
            "%s %s %s" %
            (self.children[0],
             self.children[1],
             overlap))
        if overlap[0] > overlap[1]:
            return self.children[0].search(variant_calls)
        elif overlap[1] > overlap[0]:
            return self.children[1].search(variant_calls)
        else:
            return self.samples


class Leaf(Node):

    def __init__(self, sample):

        super(Leaf, self).__init__()
        self.sample = sample

    @property
    def samples(self):
        return [self.sample]

    @property
    def is_leaf(self):
        return True

    @property
    def is_node(self):
        return False

    def search(self, variants):
        return self.sample

    def __repr__(self):
        return "Leaf : %s " % self.sample
