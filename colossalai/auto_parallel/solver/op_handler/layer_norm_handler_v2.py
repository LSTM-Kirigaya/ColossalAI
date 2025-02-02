import torch
from .node_handler import ModuleHandler
from ..sharding_strategy import ShardingStrategy_V2, OperationDataType, OperationData
from ..strategy import LayerNormGenerator, StrategyGenerator_V2
from typing import List, Dict
from .registry import operator_registry

__all__ = ['LayerNormModuleHandler']


@operator_registry.register(torch.nn.LayerNorm)
class LayerNormModuleHandler(ModuleHandler):
    """
    A LayerNormModuleHandler which deals with the sharding strategies for nn.LayerNorm module.
    """

    def get_strategy_generator(self) -> List[StrategyGenerator_V2]:
        op_data_mapping = self.get_operation_data_mapping()
        generators = []
        generators.append(LayerNormGenerator(op_data_mapping, self.device_mesh))
        return generators

    def get_operation_data_mapping(self) -> Dict[str, OperationData]:
        # use transposed shape for strategies
        # the strategies will be transformed back to its original shape in self.post_process
        physical_input_operand = OperationData(name=str(self.node.args[0]),
                                               type=OperationDataType.ARG,
                                               data=self.node.args[0]._meta_data)
        physical_other_operand = OperationData(name="weight",
                                               type=OperationDataType.PARAM,
                                               data=self.named_parameters['weight'],
                                               logical_shape=self.named_parameters['weight'].shape)
        physical_output = OperationData(name=str(self.node), type=OperationDataType.OUTPUT, data=self.node._meta_data)

        mapping = {"input": physical_input_operand, "other": physical_other_operand, "output": physical_output}

        if self.named_parameters['bias'] is not None:
            physical_bias_operand = OperationData(name="bias",
                                                  type=OperationDataType.PARAM,
                                                  data=self.named_parameters['bias'])
            mapping['bias'] = physical_bias_operand
        return mapping
