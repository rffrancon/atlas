import os
import json
from atlas.utils import unique
from atlas.utils import flatten

from atlas.schema import VariantCall
from atlas.schema import SequenceCall
from atlas.utils import get_params

from pprint import pprint


DEFAULT_MIN_GENE_CN = 0.03
DEFAULT_MIN_VARIANT_CN = 0.1


def copy_number(variant_call):
    coverage = variant_call.info.get("coverage")

    alternate_depth = coverage.get("alternate").get("median_depth")
    wt_depth = coverage.get("reference").get("median_depth")

    return float(alternate_depth) / (alternate_depth + wt_depth)


class BasePredictor(object):

    def __init__(self, variant_calls, called_genes, base_json={}):
        self.variant_or_gene_name_to_resistance_drug = {}
        self.variant_calls = variant_calls
        self.called_genes = called_genes
        self.drugs = self._get_drug_list_from_variant_to_resistance_drug()
        self.resistance_prediction = self._create_initial_resistance_prediction()
        self.out_json = base_json
        self._coveage_threshold = {
            "ermA": 0.19,
            "ermB": 0.19,
            "ermC": 0.19,
            "ermT": 0.19,
            "ermY": 0.19,
            "fusA": 0.03,
            "aacAaphD": 0.04,
            "mecA": 0.06,
            "mupA": 0.21,
            "blaZ": 0.04,
            "tetK": 0.13
        }

    def _create_initial_resistance_prediction(self):
        self.resistance_predictions = dict(
            (k, {"predict": "I"}) for k in self.drugs)

    def _get_drug_list_from_variant_to_resistance_drug(self):
        return unique(
            flatten(
                self.variant_or_gene_name_to_resistance_drug.values()))

    def predict_antibiogram(self):
        for allele_name, variant_call in self.variant_calls.items():
            self._update_resistance_prediction(allele_name, variant_call)
        # for name, gene in self.called_genes.items():
        #     self._update_resistance_prediction(gene)

    def _update_resistance_prediction(self, allele_name, variant_or_gene):
        variant_names = self._get_names(allele_name)
        for name in variant_names:
            drugs = self._get_drugs(name)
            resistance_prediction = self._resistance_prediction(
                variant_or_gene)
            for drug in drugs:
                current_resistance_prediction = self.resistance_predictions[
                    drug]["predict"]
                assert resistance_prediction is not None
                if current_resistance_prediction in ["I", "N"]:
                    self.resistance_predictions[drug][
                        "predict"] = resistance_prediction
                elif current_resistance_prediction == "S":
                    if resistance_prediction in ["r", "R"]:
                        self.resistance_predictions[drug][
                            "predict"] = resistance_prediction
                        self.resistance_predictions[drug]["called_by"] = name
                elif current_resistance_prediction == "r":
                    if resistance_prediction == "R":
                        self.resistance_predictions[drug][
                            "predict"] = resistance_prediction
                        self.resistance_predictions[drug]["called_by"] = name

    def _get_names(self, allele_name):
        names = []
        params = get_params(allele_name)
        if params.get("mut"):
            names.append("_".join([params.get("gene"), params.get("mut")]))
        names.append(allele_name.split('?')[0].split('-')[1])
        return names

    def _get_drugs(self, name, lower=False):
        if lower:
            name = name.lower()
        try:
            drugs = self.variant_or_gene_name_to_resistance_drug[name]
        except KeyError:
            try:
                drugs = self.variant_or_gene_name_to_resistance_drug[
                    name.split("-")[0]]
            except KeyError:
                talt_name = list(name)
                talt_name[-1] = "X"
                try:
                    drugs = self.variant_or_gene_name_to_resistance_drug[
                        "".join(talt_name)]
                except KeyError:
                    drugs = []
                    if not lower:
                        return self._get_drugs(name, lower=True)
                    else:
                        pass
                        # print ("Warning:NoEntry for %s" % name)
        assert drugs is not None
        return drugs

    def _resistance_prediction(self, variant_or_gene):
        if sum(variant_or_gene.genotype) == 2:
            if self._coverage_greater_than_threshold(variant_or_gene):
                return "R"
            else:
                return "S"
        elif sum(variant_or_gene.genotype) == 1:
            if self._coverage_greater_than_threshold(variant_or_gene):
                return "r"
            else:
                return "S"
        elif sum(variant_or_gene.genotype) == 0:
            return "S"
        else:
            return "I"

    def _coverage_greater_than_threshold(self, variant_or_gene):
        if isinstance(variant_or_gene, SequenceCall):
            return variant_or_gene.copy_number > self._coveage_threshold.get(
                variant_or_gene.name,
                DEFAULT_MIN_GENE_CN)
        elif isinstance(variant_or_gene, VariantCall):
            coveage_threshold = DEFAULT_MIN_VARIANT_CN
            for name in variant_or_gene.variant.names:
                if name in self._coveage_threshold:
                    coveage_threshold = self._coveage_threshold.get(
                        name, DEFAULT_MIN_VARIANT_CN)
            return copy_number(variant_or_gene) > coveage_threshold
        else:
            raise TypeError(
                "Must be either ProbeCoverage or TypedVariant object")

    def run(self):
        self.predict_antibiogram()
        self.out_json["susceptibility"] = self.resistance_predictions


def load_json(f):
    with open(f, 'r') as infile:
        return json.load(infile)


class TBPredictor(BasePredictor):

    def __init__(self, typed_variants, called_genes, base_json={}):
        super(
            TBPredictor,
            self).__init__(
            typed_variants,
            called_genes,
            base_json)        
        self.data_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                '../../data/predict/tb/'))
        self.variant_or_gene_name_to_resistance_drug = load_json(
            os.path.join(
                self.data_dir,
                "variant_to_resistance_drug.json"))



class StaphPredictor(BasePredictor):

    def __init__(self, typed_variants, called_genes, base_json={}):
        super(
            StaphPredictor,
            self).__init__(
            typed_variants,
            called_genes,
            base_json)        
        self.data_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                '../../data/predict/staph/'))
        self.variant_or_gene_name_to_resistance_drug = load_json(
            os.path.join(
                self.data_dir,
                "variant_to_resistance_drug.json"))



class GramNegPredictor(BasePredictor):

    def __init__(self, typed_variants, called_genes, base_json={}):
        self.data_dir = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                '../../data/predict/gn/'))
        self.variant_or_gene_name_to_resistance_drug = load_json(
            os.path.join(
                self.data_dir,
                "variant_to_resistance_drug.json"))
        super(
            GramNegPredictor,
            self).__init__(
            typed_variants,
            called_genes,
            base_json)
