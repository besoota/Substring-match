-- Use with the haskell/src directory of Agnishom/lregex.
module SubstringStarts
    ( startPositions, startPositionsViaTape, startPositionsViaValuations, startPositionsBaseline ) where

import Data.List (elemIndices)
import qualified Extracted as E
import Utils (wildCard)

-- | All zero-based boundaries where a match begins, in ascending order.
-- A successful zero-width match counts, including at the end of the input.
startPositions :: E.LRegex a -> [a] -> [Int]
startPositions = positionsFromTape scanStrictBits

-- | The same tape, with the unmodified evaluator's demand for Boolean values.
startPositionsViaTape :: E.LRegex a -> [a] -> [Int]
startPositionsViaTape = positionsFromTape E.cScanMatch

outerLookAhead :: E.LRegex a -> E.LRegex a
outerLookAhead regex = E.LookAhead (E.Concat regex wildCard)

positionsFromTape :: (E.ORegex a -> E.Ostring a -> E.Tape) -> E.LRegex a -> [a] -> [Int]
positionsFromTape scan regex input =
    let boundaries = length input + 1
    in case E.absEvalAux scan input (reverse input) boundaries (outerLookAhead regex) 0 [] of
        -- The single outer lookahead contributes exactly one tape to this layer.
        (_, [tape]) -> elemIndices True tape
        _ -> error "Expected one tape for the outer lookahead"

-- A lookahead reverses the list returned by scan. Force each Boolean as its
-- list cell is demanded, before reverse can retain a long chain of unevaluated bits.
scanStrictBits :: E.ORegex a -> E.Ostring a -> E.Tape
scanStrictBits regex oracleInput = forceBits (E.cScanMatch regex oracleInput)
  where
    forceBits [] = []
    forceBits (bit : rest) = bit `seq` (bit : forceBits rest)

-- | The same query through the public evaluator. Each row holds the value
-- of the outer lookahead at one input boundary, including the final boundary.
startPositionsViaValuations :: E.LRegex a -> [a] -> [Int]
startPositionsViaValuations regex input =
    let (_, valuations) = E.absEval E.cScanMatch input (outerLookAhead regex)
    in elemIndices [True] valuations

-- | Previous implementation, preserved for side-by-side timings.
startPositionsBaseline :: E.LRegex a -> [a] -> [Int]
startPositionsBaseline regex input =
    let (body, valuations) = E.absEval E.cScanMatch input regex
        -- Reversing (regex . Sigma*) puts Sigma* before the reversed body.
        search = E.rPass (E.oreverse body)
        backwardTape = E.cScanMatch search (E.orev (input, valuations))
    in elemIndices True (reverse backwardTape)
